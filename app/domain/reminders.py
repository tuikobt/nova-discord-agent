"""Phase 4A input contracts. No persistence, scheduling, or notification sending."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.core import enum_value, resource_id, text_value
from app.domain.enums import DeliveryTarget, RecurrenceType, ReminderStatus
from app.domain.errors import ValidationError
from app.domain.time import DEFAULT_TIMEZONE, as_utc, zone


def discord_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9]{1,20}", value)
        or not 0 < int(value) < 2**64
    ):
        raise ValidationError("Discord ID không hợp lệ.")
    return value


@dataclass(frozen=True, kw_only=True)
class RecurrenceRule:
    time: str
    timezone: str = DEFAULT_TIMEZONE
    weekday: int | None = None  # Monday = 0, Sunday = 6.

    def __post_init__(self):
        if not isinstance(self.time, str) or not re.fullmatch(
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", self.time
        ):
            raise ValidationError("Giờ lặp phải theo HH:MM từ 00:00 đến 23:59.")
        if not isinstance(self.timezone, str) or len(self.timezone) > 64:
            raise ValidationError("Múi giờ IANA không hợp lệ.")
        zone(self.timezone)
        if self.weekday is not None and (
            type(self.weekday) is not int or not 0 <= self.weekday <= 6
        ):
            raise ValidationError("Ngày trong tuần phải từ 0 (Thứ Hai) đến 6 (Chủ nhật).")

    @classmethod
    def from_config(cls, value: dict):
        if not isinstance(value, dict) or not (
            {"time", "timezone"} <= value.keys() <= {"time", "timezone", "weekday"}
        ):
            raise ValidationError("Quy tắc lặp cần time/timezone và weekday nếu lặp theo tuần.")
        return cls(time=value["time"], timezone=value["timezone"], weekday=value.get("weekday"))

    def to_config(self) -> dict:
        values = {"time": self.time, "timezone": self.timezone}
        if self.weekday is not None:
            values["weekday"] = self.weekday
        return values

    def matches(self, value: datetime) -> bool:
        try:
            local = as_utc(value).astimezone(zone(self.timezone))
        except (OverflowError, ValueError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("Thời gian nằm ngoài phạm vi hỗ trợ.") from None
        return (
            local.strftime("%H:%M") == self.time
            and local.second == local.microsecond == 0
            and (self.weekday is None or local.weekday() == self.weekday)
        )


def validate_recurrence(recurrence_type: str, rule: RecurrenceRule | None) -> str:
    kind = enum_value(RecurrenceType, recurrence_type)
    if kind == RecurrenceType.NONE:
        if rule is not None:
            raise ValidationError("Nhắc một lần không có quy tắc lặp.")
    elif not isinstance(rule, RecurrenceRule):
        raise ValidationError("Nhắc lặp cần quy tắc local đã xác thực.")
    elif (kind == RecurrenceType.WEEKLY) != (rule.weekday is not None):
        raise ValidationError("Weekly cần weekday; daily không có weekday.")
    return kind


@dataclass(frozen=True, kw_only=True)
class ReminderData:
    title: str
    next_fire_at: datetime
    task_id: str | None = None
    event_id: str | None = None
    recurrence_type: str = RecurrenceType.NONE
    recurrence: RecurrenceRule | None = None
    delivery_target: str = DeliveryTarget.DM
    channel_id: str | None = None
    status: str = ReminderStatus.ACTIVE

    def __post_init__(self):
        object.__setattr__(self, "title", text_value(self.title, 250))
        object.__setattr__(self, "next_fire_at", as_utc(self.next_fire_at))
        object.__setattr__(self, "status", enum_value(ReminderStatus, self.status))
        object.__setattr__(
            self, "delivery_target", enum_value(DeliveryTarget, self.delivery_target)
        )
        kind = validate_recurrence(self.recurrence_type, self.recurrence)
        object.__setattr__(self, "recurrence_type", kind)
        if self.recurrence is not None and not self.recurrence.matches(self.next_fire_at):
            raise ValidationError("Lần gửi đầu phải khớp giờ/ngày và timezone của quy tắc lặp.")
        for key in (self.task_id, self.event_id):
            if key is not None:
                resource_id(key)
        if self.delivery_target == DeliveryTarget.CHANNEL:
            discord_id(self.channel_id)
        elif self.channel_id is not None:
            raise ValidationError("Nhắc qua DM không có channel_id.")

    def validate_create(self, *, now: datetime):
        """Call at the create boundary with a backend clock; reading old rows is valid."""
        if self.next_fire_at <= as_utc(now):
            raise ValidationError("Thời gian nhắc mới phải ở tương lai.")
        if self.status in (ReminderStatus.DONE, ReminderStatus.CANCELLED):
            raise ValidationError("Không tạo nhắc mới ở trạng thái đã xong hoặc đã hủy.")
        return self

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "next_fire_at": self.next_fire_at,
            "task_id": self.task_id,
            "event_id": self.event_id,
            "recurrence_type": self.recurrence_type,
            "recurrence_config_json": self.recurrence.to_config() if self.recurrence else None,
            "delivery_target": self.delivery_target,
            "channel_id": self.channel_id,
            "status": self.status,
        }
