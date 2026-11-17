from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import AgentUsage
from app.domain.errors import ValidationError
from app.services.core_service import CoreService


class UsageService(CoreService):
    async def reserve(self, actor, config, tokens):
        owner = self.authorize(actor)
        if type(tokens) is not int or tokens <= 0:
            raise ValidationError("Reservation không hợp lệ.")
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.transaction(write=True) as session:
            count, charged = (
                await session.execute(
                    select(
                        func.count(), func.coalesce(func.sum(AgentUsage.charged_tokens), 0)
                    ).where(AgentUsage.owner_id == owner, AgentUsage.created_at >= today)
                )
            ).one()
            recent = await session.scalar(
                select(func.count())
                .select_from(AgentUsage)
                .where(
                    AgentUsage.owner_id == owner,
                    AgentUsage.created_at
                    >= datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1),
                )
            )
            if (
                count >= config.daily_requests
                or charged + tokens > config.daily_tokens
                or recent >= 12
            ):
                raise ValidationError("AI đã chạm giới hạn sử dụng. Thử lại sau hoặc dùng /menu.")
            key = str(uuid4())
            session.add(
                AgentUsage(id=key, owner_id=owner, model=config.model, charged_tokens=tokens)
            )
        return key

    async def settle(self, actor, key, usage):
        owner = self.authorize(actor)
        if not usage:
            return  # Unknown usage keeps the full reservation, including API errors.
        incoming, outgoing = usage.input_tokens, usage.output_tokens
        if type(incoming) is not int or type(outgoing) is not int or min(incoming, outgoing) < 0:
            return
        async with self.transaction(write=True) as session:
            row = await session.scalar(
                select(AgentUsage).where(AgentUsage.id == key, AgentUsage.owner_id == owner)
            )
            if row and not row.settled:
                row.input_tokens, row.output_tokens = incoming, outgoing
                row.charged_tokens, row.settled = incoming + outgoing, True

    async def summary(self, actor):
        owner = self.authorize(actor)
        async with self.transaction() as session:
            rows = (
                await session.execute(
                    select(
                        AgentUsage.model,
                        func.count(),
                        func.sum(AgentUsage.input_tokens),
                        func.sum(AgentUsage.output_tokens),
                        func.sum(AgentUsage.charged_tokens),
                    )
                    .where(AgentUsage.owner_id == owner)
                    .group_by(AgentUsage.model)
                )
            ).all()
            return [
                dict(
                    model=r[0],
                    requests=r[1],
                    input_tokens=r[2],
                    output_tokens=r[3],
                    charged_tokens=r[4],
                )
                for r in rows
            ]
