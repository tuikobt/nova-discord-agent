"""Validated personal automation settings; no Discord or persistence."""

import re
from dataclasses import dataclass
from datetime import time

from app.domain.core import text_value
from app.domain.errors import ValidationError
from app.domain.reminders import discord_id

KINDS = ("morning", "daily", "weekly")
MEMORY_KINDS = ("preference", "routine", "profile")
DEFAULTS = {"morning": "07:00", "daily": "21:30", "weekly": "20:00"}


def clock_time(value):
    try:
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError
        result = time.fromisoformat(value)
        if result.tzinfo or result.second or result.microsecond:
            raise ValueError
        return result
    except ValueError:
        raise ValidationError("Giờ phải theo HH:MM, từ 00:00 đến 23:59.") from None


@dataclass(frozen=True)
class PolicyData:
    kind: str
    enabled: bool = False
    time: str = "07:00"
    weekday: int = 6
    target: str = "dm"
    channel_id: str | None = None
    fallback: bool = False

    def __post_init__(self):
        if (
            self.kind not in KINDS
            or type(self.enabled) is not bool
            or type(self.fallback) is not bool
        ):
            raise ValidationError("Cấu hình automation không hợp lệ.")
        clock_time(self.time)
        if (
            type(self.weekday) is not int
            or not 0 <= self.weekday <= 6
            or self.target not in {"dm", "channel"}
        ):
            raise ValidationError("Ngày/vị trí gửi không hợp lệ.")
        if self.channel_id:
            discord_id(self.channel_id)
        if (self.target == "channel" or self.fallback) and not self.channel_id:
            raise ValidationError("Hãy chọn kênh riêng cho vị trí gửi/fallback.")
        if self.target == "channel" and self.fallback:
            raise ValidationError("Fallback chỉ dùng cho DM.")

    def config(self):
        return {
            "time": self.time,
            "weekday": self.weekday,
            "target": self.target,
            "channel_id": self.channel_id,
            "fallback": self.fallback,
        }


def work_config(days, start, end, break_minutes, memory_suggestions):
    if (
        not isinstance(days, list)
        or not days
        or len(set(days)) != len(days)
        or any(type(d) is not int or not 0 <= d <= 6 for d in days)
    ):
        raise ValidationError("Chọn các ngày làm việc từ thứ Hai đến Chủ nhật.")
    if clock_time(end) <= clock_time(start):
        raise ValidationError("Giờ kết thúc làm việc phải sau giờ bắt đầu trong cùng ngày.")
    if (
        type(break_minutes) is not int
        or not 0 <= break_minutes <= 120
        or type(memory_suggestions) is not bool
    ):
        raise ValidationError("Khoảng nghỉ phải từ 0–120 phút; tùy chọn memory phải là boolean.")
    return dict(
        workdays=sorted(days),
        start=start,
        end=end,
        break_minutes=break_minutes,
        memory_suggestions=memory_suggestions,
    )


def memory_content(value, secrets):
    result = text_value(value, 1000)
    if secrets.contains(result):
        raise ValidationError("Không ghi nhớ token/key hoặc private key.")
    if re.search(
        r"mật khẩu|password|số (?:thẻ|tài khoản)|căn cước|cccd|hộ chiếu|"
        r"chẩn đoán|bệnh án|tôn giáo|quan điểm chính trị|đời sống tình dục|"
        r"có lẽ|có vẻ|chắc là|suy đoán|probably|seems to",
        result.casefold(),
    ):
        raise ValidationError("Không ghi nhớ bí mật, dữ liệu nhạy cảm hoặc suy đoán về owner.")
    return result
