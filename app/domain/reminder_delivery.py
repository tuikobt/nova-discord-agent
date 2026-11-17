"""Pure recurrence, quiet-hours and delivery policy; no Discord or database access."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.domain.enums import DeliveryErrorCode
from app.domain.errors import ValidationError
from app.domain.reminders import RecurrenceRule, ReminderData
from app.domain.time import as_utc, zone

MAX_ATTEMPTS = 3
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5))
CLAIM_LEASE = timedelta(minutes=2)
CATCH_UP = timedelta(minutes=30)
ACTION_TTL = timedelta(hours=24)


def local_candidates(local: datetime, timezone: str) -> list[datetime]:
    tz = zone(timezone)
    values = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=tz, fold=fold).astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) == local:
            values.add(instant)
    return sorted(values)


def next_occurrence(rule: RecurrenceRule, after: datetime) -> datetime:
    after = as_utc(after)
    try:
        day = after.astimezone(zone(rule.timezone)).date()
        hour, minute = map(int, rule.time.split(":"))
        for offset in range(15):
            candidate_day = day + timedelta(days=offset)
            if rule.weekday is not None and candidate_day.weekday() != rule.weekday:
                continue
            candidates = local_candidates(
                datetime.combine(candidate_day, time(hour, minute)), rule.timezone
            )
            # One occurrence per local date: skip gaps; choose the first DST fold.
            if candidates and candidates[0] > after:
                return candidates[0]
    except (OverflowError, ValueError):
        pass
    raise ValidationError("Không tìm được lần nhắc tiếp theo trong phạm vi hỗ trợ.")


def quiet_until(now: datetime, timezone: str, start: time | None, end: time | None):
    if start is None or end is None:
        return None
    if start == end:
        raise ValidationError("Giờ bắt đầu và kết thúc yên lặng phải khác nhau.")
    now = as_utc(now)
    local = now.astimezone(zone(timezone))
    wall = local.time().replace(tzinfo=None)
    overnight = start > end
    inside = wall >= start or wall < end if overnight else start <= wall < end
    if not inside:
        return None
    day = local.date() + timedelta(days=1 if overnight and wall >= start else 0)
    boundary = datetime.combine(day, end)
    # If a DST change removes the boundary, use the first real minute after it.
    for minutes in range(181):
        values = [
            value
            for value in local_candidates(boundary + timedelta(minutes=minutes), timezone)
            if value > now
        ]
        if values:
            return values[0]
    raise ValidationError("Không xác định được giờ kết thúc yên lặng.")


@dataclass(frozen=True, kw_only=True)
class ReminderRecord(ReminderData):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row):
        values = {
            name: getattr(row, name)
            for name in (
                "id",
                "owner_id",
                "title",
                "next_fire_at",
                "task_id",
                "event_id",
                "recurrence_type",
                "delivery_target",
                "channel_id",
                "status",
                "created_at",
                "updated_at",
            )
        }
        values["recurrence"] = (
            RecurrenceRule.from_config(row.recurrence_config_json)
            if row.recurrence_config_json is not None
            else None
        )
        return cls(**values)

    def data(self):
        return ReminderData(
            **{name: getattr(self, name) for name in ReminderData.__dataclass_fields__}
        )


@dataclass(frozen=True)
class NotificationPreferences:
    timezone: str
    dm_enabled: bool
    channel_id: str | None
    quiet_start: time | None
    quiet_end: time | None
    updated_at: datetime


@dataclass(frozen=True)
class DeliveryRecord:
    id: str
    reminder_id: str
    scheduled_fire_at: datetime
    status: str
    attempt_count: int
    last_error_code: str | None
    finished_reason: str | None
    discord_message_id: str | None
    sent_at: datetime | None
    acknowledged_at: datetime | None
    delivery_kind: str
    retry_at: datetime | None
    claim_token: str | None

    @classmethod
    def from_row(cls, row):
        return cls(**{name: getattr(row, name) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class DeliveryClaim:
    reminder: ReminderRecord
    delivery: DeliveryRecord
    preferences: NotificationPreferences


class DeliveryFailure(Exception):
    def __init__(self, code="unknown_error", *, permanent=False):
        self.code = DeliveryErrorCode(code).value
        self.permanent = permanent
        super().__init__(self.code)
