import discord

from app.discord_bot.renderers.core import safe
from app.domain.time import format_local_datetime

STATUS = {"active": "Đang chạy", "paused": "Tạm dừng", "done": "Đã gửi", "cancelled": "Đã hủy"}
RECURRENCE = {"none": "Một lần", "daily": "Hằng ngày", "weekly": "Hằng tuần"}


def recurrence_label(record):
    value = RECURRENCE[record.recurrence_type]
    rule = record.recurrence
    if rule:
        day = (
            f"Thứ {rule.weekday + 2}"
            if rule.weekday is not None and rule.weekday < 6
            else "Chủ nhật"
            if rule.weekday == 6
            else ""
        )
        value += f" • {day} {rule.time} ({rule.timezone})"
    return value


OUTCOMES = {
    "overdue": "Bỏ qua: quá hạn hơn 30 phút",
    "superseded": "Lịch đã đổi/tạm dừng/hủy",
    "exhausted": "Hết số lần thử",
    "blocked": "Không gửi được; kiểm tra quyền/cài đặt",
}


def when(value, timezone):
    return format_local_datetime(value, timezone) if value else "Chưa chọn"


def panel(title, description):
    return discord.Embed(
        title=f"NOVA — {title}", description=description, colour=discord.Colour.blurple()
    )


def render_list(page, timezone):
    lines = [
        f"**{safe(row.title, 150)}**\n{STATUS[row.status]} • {when(row.next_fire_at, timezone)}"
        for row in page.items
    ]
    embed = panel("Reminders", "\n\n".join(lines) or "Chưa có lời nhắc. Bấm Thêm để tạo.")
    embed.set_footer(
        text=f"Trang {page.page + 1}/{max(1, (page.total + 4) // 5)} • {page.total} lời nhắc"
    )
    return embed


def render_detail(row, timezone, history, links):
    embed = panel("Chi tiết lời nhắc", safe(row.title))
    for name, value in (
        ("Trạng thái", STATUS[row.status]),
        ("Mốc lịch", when(row.next_fire_at, timezone)),
        (
            "Lặp",
            recurrence_label(row),
        ),
        (
            "Vị trí gửi",
            "DM (hoặc dự phòng đã duyệt)"
            if row.delivery_target == "dm"
            else f"<#{row.channel_id}>",
        ),
        ("Liên kết", links),
    ):
        embed.add_field(name=name, value=value, inline=False)
    states = {"pending": "Đang chờ", "claimed": "Đang xử lý", "sent": "Đã gửi", "failed": "Gửi lỗi"}
    lines = [
        f"{when(item.scheduled_fire_at, timezone)}\n"
        f"{OUTCOMES.get(item.finished_reason, states[item.status])} • {item.attempt_count} lần thử"
        + (" • Đã làm/hoãn" if item.acknowledged_at else "")
        for item in history
    ]
    embed.add_field(
        name="Lịch sử gần nhất", value="\n\n".join(lines)[:1024] or "Chưa có lần gửi.", inline=False
    )
    return embed


def render_draft(draft, links):
    embed = panel("Bản nháp lời nhắc — chưa lưu", safe(draft.title) or "Nhập tiêu đề.")
    embed.add_field(name="Thời điểm", value=when(draft.fire, draft.timezone), inline=False)
    recurrence = RECURRENCE[draft.recurrence]
    if draft.recurrence == "weekly":
        recurrence += " • " + (
            f"Thứ {draft.weekday + 2}"
            if draft.weekday is not None and draft.weekday < 6
            else "Chủ nhật"
            if draft.weekday == 6
            else "Chưa chọn ngày"
        )
    embed.add_field(name="Lặp", value=recurrence, inline=False)
    embed.add_field(
        name="Vị trí gửi",
        value="DM" if draft.target == "dm" else f"<#{draft.channel_id}>",
        inline=False,
    )
    embed.add_field(name="Liên kết", value=links, inline=False)
    embed.set_footer(
        text="Chỉ Lưu mới ghi DB. Đổi lịch/hủy cần Duyệt riêng. Bản nháp tối đa 10 phút."
    )
    return embed


def render_settings(preferences):
    channel = f"<#{preferences.channel_id}>" if preferences.channel_id else "Chưa duyệt"
    quiet = (
        f"{preferences.quiet_start:%H:%M} → {preferences.quiet_end:%H:%M}"
        if preferences.quiet_start and preferences.quiet_end
        else "Chưa bật"
    )
    return panel(
        "Cài đặt gửi lời nhắc",
        f"DM: {'Bật' if preferences.dm_enabled else 'Tắt'}\n"
        f"Kênh dự phòng: {channel}\n"
        f"Giờ yên lặng: {quiet}\nTimezone: {preferences.timezone}\n"
        "Kênh chỉ được dùng sau kiểm tra riêng tư và Duyệt. Giờ yên lặng trì hoãn lời nhắc.",
    )


def render_confirmation(before, after):
    embed = panel("Xác nhận thay đổi", "Kiểm tra trước → sau, rồi Duyệt hoặc Bỏ qua.")
    for name in after:
        if before.get(name) != after[name]:
            embed.add_field(
                name=name, value=f"{before.get(name, '—')}\n→ {after[name]}", inline=False
            )
    return embed
