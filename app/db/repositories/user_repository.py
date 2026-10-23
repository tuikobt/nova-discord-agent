from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserSettings
from app.domain.authorization import OwnerMismatchError


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_owner(self, owner_id: str, timezone: str) -> None:
        other_owner = await self.session.scalar(
            select(User.discord_user_id).where(User.discord_user_id != owner_id).limit(1)
        )
        if other_owner is not None:
            raise OwnerMismatchError("Database thuộc owner khác; kiểm tra DISCORD_OWNER_ID.")
        user = await self.session.get(User, owner_id)
        if user is None:
            self.session.add(User(discord_user_id=owner_id, timezone=timezone, locale="vi-VN"))
            await self.session.flush()
        if await self.session.get(UserSettings, owner_id) is None:
            self.session.add(UserSettings(owner_id=owner_id))
