"""Legacy button/select editors. Choosing values only changes a private draft."""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from time import monotonic

import discord

from app.discord_bot.renderers.core import LABELS, safe
from app.discord_bot.views.core import CoreView, choices
from app.domain.enums import ProjectStatus, TaskPriority
from app.domain.modules import Screen

MINUTES = (15, 30, 45, 60, 90, 120, 180, 240)


def bounded(view, expires_at):
    view.expires_at = min(view.expires_at, expires_at)
    view.timeout = max(0.1, view.expires_at - monotonic())


class DraftView(CoreView):
    def __init__(self, core, draft):
        super().__init__(core, draft.route, draft.timezone)
        self.draft = draft
        bounded(self, draft.expires_at)
        self.button("Bỏ bản nháp", "draft_cancel")
        self.button("Sửa nội dung", "draft_text")
        self.button("Lưu", "draft_save", style=discord.ButtonStyle.success)
        self.button(
            "Nhập ngày/giờ, số phút"
            if self.route.screen == Screen.TASKS
            else "Nhập ngày/giờ chính xác",
            "draft_exact",
            row=4,
        )
        values = draft.values()
        if self.route.screen == Screen.CALENDAR:
            self.button("Chọn bắt đầu", "draft_date", row=1, value="starts_at")
            self.button("Chọn kết thúc", "draft_date", row=1, value="ends_at")
            fixed = draft.selections.get(
                "is_fixed", draft.record.is_fixed if draft.record else False
            )
            self.select(
                "draft_fixed",
                [
                    discord.SelectOption(label="Cố định", value="yes", default=fixed),
                    discord.SelectOption(label="Linh hoạt", value="no", default=not fixed),
                ],
                row=2,
                placeholder="Chọn loại lịch…",
            )
            self.select(
                "draft_duration",
                [discord.SelectOption(label=f"{n} phút", value=str(n)) for n in MINUTES],
                row=3,
                placeholder="Đặt kết thúc sau bắt đầu…",
            )
            self.button("Chọn công việc", "draft_link", row=4)
        else:
            key = "due_at" if self.route.screen == Screen.TASKS else "deadline_at"
            self.button("Chọn deadline", "draft_date", row=1, value=key)
            self.button("Bỏ deadline", "draft_clear", row=1, value=key)
            if self.route.screen == Screen.TASKS:
                current = draft.selections.get(
                    "priority", draft.record.priority if draft.record else "medium"
                )
                self.select(
                    "draft_priority",
                    choices(TaskPriority, current),
                    row=2,
                    placeholder="Chọn ưu tiên…",
                )
                current_minutes = values["estimated_minutes"]
                minutes = dict.fromkeys(
                    [*map(str, MINUTES), *([current_minutes] if current_minutes else [])]
                )
                self.select(
                    "draft_estimate",
                    [
                        discord.SelectOption(
                            label="Chưa ước tính", value="none", default=not current_minutes
                        )
                    ]
                    + [
                        discord.SelectOption(
                            label=f"{n} phút", value=n, default=n == current_minutes
                        )
                        for n in minutes
                    ],
                    row=3,
                    placeholder="Chọn thời lượng ước tính…",
                )
                self.button("Chọn dự án", "draft_link", row=4)
            else:
                current = draft.selections.get(
                    "status", draft.record.status if draft.record else "active"
                )
                self.select(
                    "draft_status",
                    choices(ProjectStatus, current),
                    row=2,
                    placeholder="Chọn trạng thái dự án…",
                )


def render_draft(draft, *, link_name=None, notice=None):
    values = draft.values()
    label = values.get("name", values.get("title", ""))
    embed = discord.Embed(
        title="NOVA — Xem lại trước khi lưu",
        description=(notice + "\n\n" if notice else "")
        + "**Bản nháp chưa lưu.** Chọn ngày/giờ trong các menu, kiểm tra rồi bấm Lưu.\n"
        + f"Múi giờ: {draft.timezone}",
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Tên / Tiêu đề", value=safe(label, 500) or "Chưa nhập", inline=False)
    if values.get("description"):
        embed.add_field(name="Mô tả", value=safe(values["description"], 1000), inline=False)
    for key, name in (
        ("deadline_at", "Deadline"),
        ("due_at", "Deadline"),
        ("starts_at", "Bắt đầu"),
        ("ends_at", "Kết thúc"),
    ):
        if key in values:
            embed.add_field(name=name, value=safe(values[key] or "Chưa chọn"), inline=False)
    if draft.route.screen == Screen.CALENDAR:
        fixed = draft.selections.get("is_fixed", draft.record.is_fixed if draft.record else False)
        embed.add_field(name="Loại lịch", value="Cố định" if fixed else "Linh hoạt")
    elif draft.route.screen == Screen.TASKS:
        priority = draft.selections.get(
            "priority", draft.record.priority if draft.record else "medium"
        )
        embed.add_field(name="Ưu tiên", value=LABELS[priority])
        embed.add_field(
            name="Ước tính",
            value=f"{values['estimated_minutes']} phút"
            if values["estimated_minutes"]
            else "Chưa đặt",
        )
    else:
        status = draft.selections.get("status", draft.record.status if draft.record else "active")
        embed.add_field(name="Trạng thái", value=LABELS[status])
    if draft.route.screen != Screen.PROJECTS:
        embed.add_field(
            name="Liên kết",
            value=safe(link_name) if link_name else "Không gắn liên kết",
            inline=False,
        )
    embed.set_footer(
        text="Chỉ ghi database khi Lưu và duyệt nếu cần • Bản nháp hết hạn sau 10 phút"
    )
    return embed


@dataclass(frozen=True)
class DeadlineRange:
    route: object
    timezone: str
    start: date | None = None
    end: date | None = None
    expires_at: float = field(default_factory=lambda: monotonic() + 600)


class DeadlineRangeView(CoreView):
    def __init__(self, core, state):
        super().__init__(core, state.route, state.timezone)
        self.state = state
        bounded(self, state.expires_at)
        self.button("Quay lại", "range_cancel")
        self.button("Từ ngày", "range_date", row=1, value="start")
        self.button("Đến hết ngày", "range_date", row=1, value="end")
        self.button("Bỏ mốc từ", "range_clear", row=2, value="start")
        self.button("Bỏ mốc đến", "range_clear", row=2, value="end")
        self.button("Hôm nay", "range_today", row=3)
        self.button("7 ngày tới", "range_week", row=3)
        self.button("Áp dụng", "range_apply", row=3, style=discord.ButtonStyle.primary)


def render_range(state, notice=None):
    def label(value):
        return f"{value:%d/%m/%Y}" if value else "Không giới hạn"

    return discord.Embed(
        title="NOVA — Chọn khoảng deadline",
        description=(notice + "\n\n" if notice else "")
        + f"Từ ngày: **{label(state.start)}**\nĐến hết ngày: **{label(state.end)}**\n"
        + f"Múi giờ: {state.timezone}\nChọn bằng nút, sau đó bấm Áp dụng.",
        colour=discord.Colour.blurple(),
    )


@dataclass(frozen=True)
class DateChoice:
    route: object
    timezone: str
    target: object
    field: str
    selected: datetime  # local wall time, validated for DST only when explicitly applied
    expires_at: float
    date_only: bool = False


class DatePickerView(CoreView):
    def __init__(self, core, state):
        super().__init__(core, state.route, state.timezone)
        self.state = state
        bounded(self, state.expires_at)
        selected = state.selected
        month_index = (selected.year - 1) * 12 + selected.month - 1
        self.button("‹ Tháng", "picker_month", value=-1, disabled=month_index == 0)
        self.button("Tháng ›", "picker_month", value=1, disabled=month_index == 9999 * 12 - 1)
        self.button("Hôm nay", "picker_today")
        self.button("Quay lại", "picker_cancel")
        self.button(
            "Dùng ngày" if state.date_only else "Dùng ngày giờ",
            "picker_apply",
            style=discord.ButtonStyle.primary,
        )
        last = calendar.monthrange(selected.year, selected.month)[1]
        for row, start, stop in ((1, 1, min(16, last)), (2, 17, last)):
            self.select(
                "picker_day" if row == 1 else "picker_day_late",
                [
                    discord.SelectOption(
                        label=f"Ngày {n:02d}", value=str(n), default=n == selected.day
                    )
                    for n in range(start, stop + 1)
                ],
                row=row,
                placeholder=f"Chọn ngày {start:02d}–{stop:02d}…",
            )
        if not state.date_only:
            self.select(
                "picker_hour",
                [
                    discord.SelectOption(
                        label=f"{n:02d} giờ", value=str(n), default=n == selected.hour
                    )
                    for n in range(24)
                ],
                row=3,
                placeholder="Chọn giờ 00–23…",
            )
            self.select(
                "picker_minute",
                [
                    discord.SelectOption(
                        label=f"{n:02d} phút", value=str(n), default=n == selected.minute
                    )
                    for n in sorted({*range(0, 60, 5), selected.minute})
                ],
                row=4,
                placeholder="Chọn phút (bước 5 phút)…",
            )
        else:
            self.button("Ngày mai", "picker_tomorrow", row=3)


def render_date_picker(state, notice=None):
    selected = state.selected
    # Calendar(firstweekday=0) is independent of any process-global calendar settings.
    grid = calendar.Calendar(firstweekday=0).monthdayscalendar(selected.year, selected.month)
    text = " T2 T3 T4 T5 T6 T7 CN\n" + "\n".join(
        " ".join(f"{n:3d}" if n else "   " for n in week) for week in grid
    )
    value = f"{selected:%d/%m/%Y}" + ("" if state.date_only else f" {selected:%H:%M}")
    label = {
        "starts_at": "Bắt đầu",
        "ends_at": "Kết thúc",
        "due_at": "Deadline",
        "deadline_at": "Deadline",
        "start": "Từ ngày",
        "end": "Đến hết ngày",
        "day": "Ngày xem lịch",
    }[state.field]
    return discord.Embed(
        title=f"NOVA — Chọn {label.lower()}",
        description=(notice + "\n\n" if notice else "")
        + f"**Tháng {selected.month:02d}/{selected.year:04d}**\n```\n{text}\n```\n"
        + f"Đang chọn: **{value}** • {state.timezone}\n"
        + "Chọn ngày trong hai menu bên dưới; dùng ‹/› để đổi tháng.\n"
        + (
            ""
            if state.date_only
            else "Giờ/phút chọn trong menu. Cần phút khác: quay lại → Nhập ngày/giờ chính xác.\n"
        )
        + "Chỉ áp dụng khi bấm Dùng ngày; chưa lưu database.",
        colour=discord.Colour.blurple(),
    )


class DraftLinkView(CoreView):
    def __init__(self, core, draft, page):
        super().__init__(core, draft.route, draft.timezone)
        self.draft, self.link_page = draft, page.page
        bounded(self, draft.expires_at)
        self.button("Về bản nháp", "draft_link_back")
        options = [discord.SelectOption(label="Không gắn liên kết", value="none")]
        options += [
            discord.SelectOption(
                label=safe(getattr(row, "name", getattr(row, "title", "")), 90), value=row.id
            )
            for row in page.items
        ]
        self.select("draft_link_value", options, row=1, placeholder="Chọn dự án / công việc…")
        self.pages(page.page, page.total, page.page_size, row=2, action="draft_link_page")
