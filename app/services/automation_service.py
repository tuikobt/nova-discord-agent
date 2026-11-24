"""Durable, opt-in report runs. Never holds a DB transaction across an API call."""

import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update

from app.db.models import AutomationPolicy, AutomationRun, User, UserSettings
from app.domain.errors import ValidationError
from app.domain.personal import KINDS
from app.domain.reminder_delivery import quiet_until
from app.domain.time import parse_local_datetime, zone
from app.services.core_service import CoreService


class AutomationService(CoreService):
    def __init__(self, sessions, authorization, personal, reports):
        super().__init__(sessions, authorization)
        self.personal, self.reports = personal, reports
        self.lock = asyncio.Lock()

    async def enqueue(self, actor):
        owner = self.authorize(actor)
        now = self.personal.clock()
        async with self.transaction(write=True) as session:
            user = await session.get(User, owner)
            today = now.astimezone(zone(user.timezone)).date()
            policies = await self.personal.policy_rows(session, owner)
            for kind in KINDS:
                policy = policies.get(kind)
                if not policy or not policy.enabled:
                    continue
                for date_value in (today - timedelta(days=1), today):
                    if kind == "weekly" and date_value.weekday() != policy.config_json["weekday"]:
                        continue
                    try:
                        due = parse_local_datetime(
                            f"{date_value} {policy.config_json['time']}", user.timezone
                        )
                    except (ValueError, ValidationError):
                        continue
                    if due > now:
                        continue
                    period = (
                        date_value - timedelta(days=date_value.weekday())
                        if kind == "weekly"
                        else date_value
                    ).isoformat()
                    existing = await session.scalar(
                        select(AutomationRun.id).where(
                            AutomationRun.owner_id == owner,
                            AutomationRun.kind == kind,
                            AutomationRun.period_key == period,
                        )
                    )
                    if existing:
                        continue
                    reason = (
                        "policy_changed"
                        if due < policy.updated_at
                        else "overdue"
                        if due + timedelta(hours=2) < now
                        else None
                    )
                    session.add(
                        AutomationRun(
                            id=str(uuid4()),
                            owner_id=owner,
                            kind=kind,
                            period_key=period,
                            timezone=user.timezone,
                            scheduled_at=due,
                            expires_at=due + timedelta(hours=2),
                            policy_version=policy.version,
                            created_at=now,
                            status="skipped" if reason else "pending",
                            error_code=reason,
                        )
                    )
            # Remove only report content, preserving keys/metadata for duplicate prevention.
            await session.execute(
                update(AutomationRun)
                .where(
                    AutomationRun.owner_id == owner,
                    AutomationRun.created_at < now - timedelta(days=30),
                )
                .values(payload_json=None)
            )

    async def due(self, actor):
        owner = self.authorize(actor)
        now = self.personal.clock()
        async with self.transaction() as session:
            rows = await session.scalars(
                select(AutomationRun.id)
                .where(
                    AutomationRun.owner_id == owner,
                    AutomationRun.status.in_(["pending", "claimed"]),
                    or_(AutomationRun.retry_at.is_(None), AutomationRun.retry_at <= now),
                )
                .order_by(AutomationRun.scheduled_at)
                .limit(10)
            )
            return tuple(rows)

    async def claim(self, actor, key):
        owner = self.authorize(actor)
        now = self.personal.clock()
        async with self.transaction(write=True) as session:
            row = await session.scalar(
                select(AutomationRun).where(
                    AutomationRun.id == key, AutomationRun.owner_id == owner
                )
            )
            if row is None or row.status not in {"pending", "claimed"}:
                return None
            if row.status == "claimed" and row.claimed_at + timedelta(minutes=2) > now:
                return None
            policy = await session.scalar(
                select(AutomationPolicy).where(
                    AutomationPolicy.owner_id == owner, AutomationPolicy.kind == row.kind
                )
            )
            if not policy or not policy.enabled or row.policy_version != policy.version:
                row.status, row.error_code = "skipped", "policy_changed"
                return None
            if row.expires_at < now or row.attempt_count >= 3:
                row.status, row.error_code = (
                    "skipped",
                    "overdue" if row.expires_at < now else "exhausted",
                )
                return None
            if row.retry_at and row.retry_at > now:
                return None
            user, settings = await session.get(User, owner), await session.get(UserSettings, owner)
            if user.timezone != row.timezone:
                row.status, row.error_code = "skipped", "policy_changed"
                return None
            delayed = quiet_until(now, user.timezone, settings.quiet_start, settings.quiet_end)
            if delayed:
                row.status, row.retry_at = "pending", delayed
                return None
            row.status, row.claim_token, row.claimed_at = "claimed", str(uuid4()), now
            row.attempt_count += 1
            return dict(
                id=row.id,
                kind=row.kind,
                token=row.claim_token,
                attempt=row.attempt_count,
                period=row.period_key,
                scheduled_at=row.scheduled_at,
                policy_version=row.policy_version,
                payload=row.payload_json,
                timezone=user.timezone,
                settings_updated_at=settings.updated_at.isoformat(),
            )

    async def ready_to_send(self, actor, claim):
        owner = self.authorize(actor)
        now = self.personal.clock()
        async with self.transaction() as session:
            row = await session.scalar(
                select(AutomationRun).where(
                    AutomationRun.id == claim["id"], AutomationRun.owner_id == owner
                )
            )
            config = await self.personal.configuration(session, owner)
            policy = config["policies"][claim["kind"]]
            settings = await session.get(UserSettings, owner)
            if (
                row is None
                or row.claim_token != claim["token"]
                or row.status != "claimed"
                or row.expires_at < now
                or not policy["enabled"]
                or policy["version"] != claim["policy_version"]
                or config["timezone"] != claim["timezone"]
                or settings.updated_at.isoformat() != claim["settings_updated_at"]
                or quiet_until(now, config["timezone"], settings.quiet_start, settings.quiet_end)
            ):
                return None
            return dict(policy=policy, dm_enabled=settings.dm_notifications_enabled)

    async def finish(self, actor, claim, *, payload=None, message=None, error=None):
        owner = self.authorize(actor)
        if error not in {
            None,
            "forbidden",
            "network_error",
            "timeout",
            "http_error",
            "policy_changed",
            "unknown_error",
        }:
            error = "unknown_error"
        async with self.transaction(write=True) as session:
            row = await session.scalar(
                select(AutomationRun).where(
                    AutomationRun.id == claim["id"], AutomationRun.owner_id == owner
                )
            )
            if row is None or row.status != "claimed" or row.claim_token != claim["token"]:
                return
            row.payload_json = payload
            row.claim_token = None
            if message:
                row.status, row.sent_at = "sent", self.personal.clock()
                row.discord_message_id, row.channel_id = str(message[0]), str(message[1])
                row.error_code, row.retry_at = None, None
            else:
                row.error_code = error or "unknown_error"
                permanent = error in {"forbidden", "policy_changed"} or row.attempt_count >= 3
                row.status = "failed" if permanent else "pending"
                row.retry_at = (
                    None
                    if permanent
                    else self.personal.clock()
                    + timedelta(minutes=1 if row.attempt_count == 1 else 5)
                )

    async def tick(self, sender):
        actor = self.authorization.owner_id
        self.authorization.require_owner(actor)
        async with self.lock:
            await self.enqueue(actor)
            for key in await self.due(actor):
                claim = await self.claim(actor, key)
                if not claim:
                    continue
                payload = claim["payload"]
                try:
                    if payload is None:
                        local_day = claim["scheduled_at"].astimezone(zone(claim["timezone"])).date()
                        payload = await self.reports.build(
                            actor, claim["kind"], period=local_day, background=True
                        )
                    routing = await self.ready_to_send(actor, claim)
                    if routing is None:
                        await self.finish(actor, claim, payload=payload, error="policy_changed")
                        continue
                    message = await asyncio.wait_for(
                        sender.send(actor, claim["id"], payload, routing), timeout=10
                    )
                    await self.finish(actor, claim, payload=payload, message=message)
                except Exception as error:
                    code = (
                        "timeout"
                        if isinstance(error, TimeoutError)
                        else getattr(error, "code", "unknown_error")
                    )
                    await self.finish(actor, claim, payload=payload, error=code)
