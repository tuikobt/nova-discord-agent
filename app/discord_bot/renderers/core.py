"""Legacy embeds from immutable results; escape content and obey Discord limits."""

from dataclasses import fields
from datetime import datetime

import discord

from app.domain.core import EventRecord, ProjectRecord, TaskRecord
from app.domain.modules import MODULES, Screen
from app.domain.time import format_local_datetime

LABELS = {
    "todo": "Cần làm",
    "doing": "Đang làm",
    "done": "Hoàn thành",
    "cancelled": "Đã hủy",
    "active": "Đang chạy",
    "paused": "Tạm dừng",
    "completed": "Hoàn tất",
    "archived": "Lưu trữ",
    "proposed": "Đề xuất",
    "confirmed": "Đã xác nhận",
    "low": "Thấp",
    "medium": "Vừa",
    "high": "Cao",
    "critical": "Khẩn cấp",
}
FIELD_LABELS = {
    "name": "Tên dự án",
    "title": "Tiêu đề",
    "description": "Mô tả",
    "status": "Trạng thái",
    "priority": "Ưu tiên",
    "deadline_at": "Deadline",
    "due_at": "Deadline",
    "estimated_minutes": "Ước tính (phút)",
    "project_id": "Dự án",
    "task_id": "Công việc",
    "starts_at": "Bắt đầu",
    "ends_at": "Kết thúc",
    "is_fixed": "Lịch cố định",
}


def safe(value, limit=1024):
    text = discord.utils.escape_mentions(discord.utils.escape_markdown(str(value)))
    return text if len(text) <= limit else text[: limit - 35] + "… (mở Sửa để xem đầy đủ)"


def when(value, timezone):
    return format_local_datetime(value, timezone) if value else "Chưa đặt"


def record_label(record):
    return record.name if isinstance(record, ProjectRecord) else record.title


def record_lines(record, timezone, *, link_name=None, progress=None):
    lines = [f"**{safe(record_label(record), 500)}**", f"Trạng thái: {LABELS[record.status]}"]
    if isinstance(record, TaskRecord):
        lines += [
            f"Ưu tiên: {LABELS[record.priority]}",
            f"Deadline: {when(record.due_at, timezone)}",
        ]
        lines += [
            f"Dự án: {safe(link_name) if link_name else 'Không gắn dự án'}",
            f"Ước tính: {record.estimated_minutes or 'Chưa đặt'} phút",
            f"Hoàn thành lúc: {when(record.completed_at, timezone)}",
        ]
    elif isinstance(record, ProjectRecord):
        lines += [f"Deadline: {when(record.deadline_at, timezone)}"]
        if progress is not None:
            lines += [
                f"Tiến độ: {progress.percent:.0f}% ({progress.done}/{progress.total})",
                progress.description,
            ]
    else:
        lines += [
            f"{when(record.starts_at, timezone)} → {when(record.ends_at, timezone)}",
            f"Lịch cố định: {'Có' if record.is_fixed else 'Không'}",
            f"Công việc: {safe(link_name) if link_name else 'Không gắn công việc'}",
        ]
    return "\n".join(lines)


def render_list(route, page, timezone, *, progress=None, project_name=None):
    embed = discord.Embed(
        title=f"NOVA — {MODULES[route.screen].title}", colour=discord.Colour.blurple()
    )
    filters = [
        f"{timezone} • {page.total} bản ghi",
        f"Trạng thái: {LABELS.get(route.status, 'Tất cả')}",
    ]
    if route.screen == Screen.TASKS:
        filters += [f"Ưu tiên: {LABELS.get(route.priority, 'Tất cả')}"]
        if project_name:
            filters += [f"Dự án: {safe(project_name, 250)}"]
        if route.due_from or route.due_until:
            filters += [
                f"Deadline: từ {when(route.due_from, timezone)} "
                f"đến trước {when(route.due_until, timezone)}"
            ]
    if route.screen == Screen.CALENDAR:
        filters += [f"{'Tuần chứa ngày' if route.weekly else 'Ngày'} {route.day:%d/%m/%Y}"]
    embed.description = "\n".join(filters)
    for record in page.items:
        value = f"{LABELS[record.status]}"
        if isinstance(record, TaskRecord):
            value += f" • {LABELS[record.priority]}\nDeadline: {when(record.due_at, timezone)}"
        elif isinstance(record, EventRecord):
            value += f"\n{when(record.starts_at, timezone)} → {when(record.ends_at, timezone)}"
        elif progress is not None:
            metric = progress[record.id]
            value += (
                f" • {metric.percent:.0f}% ({metric.done}/{metric.total} task)"
                if metric.total
                else " • 0% — Chưa có nhiệm vụ"
            )
        embed.add_field(name=safe(record_label(record), 250), value=value, inline=False)
    if not page.items:
        embed.add_field(
            name="Chưa có bản ghi phù hợp", value="Bấm Thêm để tạo hoặc đổi bộ lọc.", inline=False
        )
    if route.screen == Screen.PROJECTS:
        embed.add_field(
            name="Cách tính tiến độ",
            value="Task done / task không hủy; tính theo số lượng task.",
            inline=False,
        )
    total_pages = max(1, (page.total + page.page_size - 1) // page.page_size)
    embed.set_footer(text=f"NOVA • Trang {page.page + 1}/{total_pages} • Chọn mục để xem chi tiết")
    return embed


def render_detail(screen, record, timezone, *, link_name=None, progress=None):
    embed = discord.Embed(
        title=f"NOVA — {MODULES[screen].title}",
        colour=discord.Colour.blurple(),
        description=record_lines(record, timezone, link_name=link_name, progress=progress),
    )
    if getattr(record, "description", None):
        embed.add_field(name="Mô tả", value=safe(record.description, 1000), inline=False)
    embed.set_footer(text="NOVA • Thay đổi task không tự đổi lịch liên kết • Back / Refresh")
    return embed


def render_today(day, timezone, events, tasks, task_total):
    embed = discord.Embed(
        title="NOVA — Today Dashboard",
        colour=discord.Colour.blurple(),
        description=f"{day:%d/%m/%Y} • {timezone}",
    )
    embed.add_field(
        name=f"Lịch confirmed hôm nay ({events.total})",
        inline=False,
        value=(
            "\n".join(
                f"• {safe(row.title, 180)} — {when(row.starts_at, timezone)}"
                for row in events.items
            )
            or "Chưa có lịch hôm nay. Bấm Thêm lịch."
        )[:1024],
    )
    embed.add_field(
        name=f"Việc đến hạn/quá hạn hoặc ưu tiên cao ({task_total})",
        inline=False,
        value="\n".join(f"• {safe(row.title, 140)} • {LABELS[row.priority]}" for row in tasks)
        or "Chưa có công việc phù hợp.",
    )
    embed.set_footer(text="NOVA • Tối đa 5 mục mỗi nhóm • Mở module để xem tất cả")
    return embed


def confirmation_pages(request, timezone, link_names):
    def display(name, value):
        if value is None:
            return "Không đặt"
        if isinstance(value, datetime):
            return when(value, timezone)
        if isinstance(value, bool):
            return "Có" if value else "Không"
        if name in ("project_id", "task_id"):
            return link_names.get(value, "Liên kết không còn sẵn có")
        return LABELS.get(value, str(value)) if name in ("status", "priority") else str(value)

    lines = ["Xem thay đổi trước khi duyệt. Bỏ qua sẽ không ghi dữ liệu.", f"Múi giờ: {timezone}"]
    for field in fields(request.after):
        old = getattr(request.before, field.name, None)
        new = getattr(request.after, field.name)
        if request.before is None or old != new:
            lines += [
                f"\n**{FIELD_LABELS[field.name]}**",
                "Trước: " + safe(display(field.name, old), 20000),
                "Sau: " + safe(display(field.name, new), 20000),
            ]
    if request.conflicts:
        lines += [f"\n**Có {len(request.conflicts)} lịch trùng. Duyệt sẽ giữ cả các lịch này:**"]
        lines += [
            f"• {safe(row.title, 1000)}: {when(row.starts_at, timezone)} "
            f"→ {when(row.ends_at, timezone)}"
            for row in request.conflicts
        ]
    text = "\n".join(lines)
    return tuple(text[index : index + 3300] for index in range(0, len(text), 3300))


def render_confirmation(request, pages, page):
    embed = discord.Embed(
        title="NOVA — Xác nhận thay đổi", description=pages[page], colour=discord.Colour.orange()
    )
    embed.set_footer(
        text=f"Trang {page + 1}/{len(pages)} • Duyệt ở trang cuối • Hết hạn sau tối đa 5 phút"
    )
    return embed
