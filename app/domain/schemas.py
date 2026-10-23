"""Immutable view models without Discord or ORM dependencies."""

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class DashboardLocation:
    channel_id: int
    message_id: int

    def __post_init__(self) -> None:
        for value in (self.channel_id, self.message_id):
            if type(value) is not int or not 0 < value < 2**64:
                raise ValueError("Discord ID không hợp lệ.")


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    timezone: str
    locale: str
    morning_briefing_time: time | None
    daily_review_time: time | None
    dm_notifications_enabled: bool
    dashboard: DashboardLocation | None


@dataclass(frozen=True, slots=True)
class DashboardOverview:
    today: date
    timezone: str
    # None means unavailable, rather than a measured zero.
    tasks: int | None = None
    projects: int | None = None
    reminders: int | None = None


@dataclass(frozen=True, slots=True)
class FeaturePage:
    items: tuple[str, ...]
    index: int
    total: int


def paginate(items: tuple[str, ...], index: int = 0, size: int = 4) -> FeaturePage:
    if size < 1:
        raise ValueError("Kích thước trang phải lớn hơn 0.")
    total = max(1, (len(items) + size - 1) // size)
    if type(index) is not int or not 0 <= index < total:
        raise ValueError("Trang không hợp lệ; hãy quay lại Dashboard.")
    return FeaturePage(items[index * size : (index + 1) * size], index, total)
