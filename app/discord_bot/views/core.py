"""Private legacy Views: paging, record selection, forms and explicit confirmations."""

from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

import discord

from app.discord_bot.error_handlers import send_private
from app.discord_bot.renderers.core import LABELS, record_label
from app.discord_bot.views.dashboard import OwnerView
from app.domain.core import ProjectRecord, TaskRecord
from app.domain.enums import EventStatus, ProjectStatus, TaskPriority, TaskStatus
from app.domain.modules import Screen


class CoreView(OwnerView):
    def __init__(self, core, route, timezone):
        super().__init__(core.dashboard)
        self.core, self.route, self.timezone = core, route, timezone

    async def guard(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if self.is_finished():
            await send_private(interaction, "Màn hình đã đổi. Dùng Refresh trên panel đang mở.")
            return False
        return True

    async def interaction_check(self, interaction):
        return await self.guard(interaction)

    async def on_error(self, interaction, error, item):
        await self.core.error(interaction, error, self.route, self)

    def button(
        self,
        label,
        action,
        *,
        row=0,
        value=None,
        disabled=False,
        style=discord.ButtonStyle.secondary,
    ):
        self.add_item(
            CoreButton(label, action, row=row, value=value, disabled=disabled, style=style)
        )

    def select(self, action, options, *, row, placeholder):
        if options:
            self.add_item(CoreSelect(action, options, row=row, placeholder=placeholder))

    def pages(self, page, total, size, *, row=4, action="page"):
        self.button("Previous", action, row=row, value=page - 1, disabled=page == 0)
        self.button("Next", action, row=row, value=page + 1, disabled=(page + 1) * size >= total)


class CoreButton(discord.ui.Button):
    def __init__(self, label, action, *, row, value, disabled, style):
        super().__init__(
            label=label,
            row=row,
            disabled=disabled,
            style=style,
            custom_id=f"nova:core:v1:{action}:{uuid4().hex[:12]}",
        )
        self.action, self.value = action, value

    async def callback(self, interaction):
        if await self.view.guard(interaction):
            await self.view.core.dispatch(interaction, self.view, self.action, self.value)


class CoreSelect(discord.ui.Select):
    def __init__(self, action, options, *, row, placeholder):
        super().__init__(
            options=options, row=row, placeholder=placeholder, custom_id=f"nova:core:v1:{action}"
        )
        self.action = action

    async def callback(self, interaction):
        if not await self.view.guard(interaction):
            return
        if len(self.values) != 1 or self.values[0] not in {option.value for option in self.options}:
            await send_private(interaction, "Lựa chọn không hợp lệ. Hãy Refresh.")
            return
        await self.view.core.dispatch(interaction, self.view, self.action, self.values[0])


def choices(values, current=None, *, all_items=False):
    options = (
        [discord.SelectOption(label="Tất cả", value="all", default=current is None)]
        if all_items
        else []
    )
    return options + [
        discord.SelectOption(label=LABELS[value], value=value, default=value == current)
        for value in values
    ]


def record_options(records):
    def kind(row):
        return (
            Screen.PROJECTS
            if isinstance(row, ProjectRecord)
            else Screen.TASKS
            if isinstance(row, TaskRecord)
            else Screen.CALENDAR
        )

    return [
        discord.SelectOption(
            label=record_label(row)[:100],
            value=f"{kind(row).value}:{row.id}",
            description=LABELS[row.status],
        )
        for row in records
    ]


class CorePanelView(CoreView):
    def __init__(self, core, route, timezone, *, page=None, record=None, today_records=()):
        super().__init__(core, route, timezone)
        self.record = record
        self.button("Back", "back")
        self.button("Refresh", "refresh")
        if route.screen == Screen.TODAY:
            self.button("Thêm lịch", "new_event")
            self.button("Thêm task", "new_task")
            self.button("Xem lịch", "today_calendar")
            self.select(
                "record",
                record_options(today_records),
                row=1,
                placeholder="Xem chi tiết task/lịch…",
            )
            self.button("Tất cả tasks", "today_tasks", row=2)
            return
        if record is not None:
            self.button("Sửa", "edit")
            if isinstance(record, TaskRecord):
                self.button(
                    "Mở lại" if record.status in ("done", "cancelled") else "Hoàn thành",
                    "task_done",
                )
                self.button("Lên lịch", "new_event")
                self.select(
                    "priority",
                    choices(TaskPriority, record.priority),
                    row=2,
                    placeholder="Đổi ưu tiên…",
                )
                self.button("Đổi dự án", "pick_link", row=3)
            elif isinstance(record, ProjectRecord):
                self.button("Xem tasks", "project_tasks")
                self.button("Thêm task", "new_task")
            else:
                self.button("Đổi task", "pick_link")
                self.select(
                    "fixed",
                    [
                        discord.SelectOption(label="Cố định", value="yes", default=record.is_fixed),
                        discord.SelectOption(
                            label="Linh hoạt", value="no", default=not record.is_fixed
                        ),
                    ],
                    row=2,
                    placeholder="Loại khung giờ…",
                )
            states = (
                ProjectStatus
                if isinstance(record, ProjectRecord)
                else TaskStatus
                if isinstance(record, TaskRecord)
                else EventStatus
            )
            self.select(
                "status", choices(states, record.status), row=1, placeholder="Đổi trạng thái…"
            )
            return
        self.button("Thêm", "add", style=discord.ButtonStyle.primary)
        self.select(
            "record", record_options(page.items), row=1, placeholder="Chọn bản ghi để xem / sửa…"
        )
        states = (
            ProjectStatus
            if route.screen == Screen.PROJECTS
            else TaskStatus
            if route.screen == Screen.TASKS
            else EventStatus
        )
        self.select(
            "filter_status",
            choices(states, route.status, all_items=True),
            row=2,
            placeholder="Lọc trạng thái…",
        )
        if route.screen == Screen.TASKS:
            self.button("Deadline", "date")
            self.button("Dự án", "filter_project")
            self.select(
                "filter_priority",
                choices(TaskPriority, route.priority, all_items=True),
                row=3,
                placeholder="Lọc ưu tiên…",
            )
        if route.screen == Screen.CALENDAR:
            self.button("Chọn ngày", "date")
            self.button("Xem ngày" if route.weekly else "Xem tuần", "week")
            self.button("← Tuần" if route.weekly else "← Ngày", "shift", row=3, value=-1)
            self.button("Tuần →" if route.weekly else "Ngày →", "shift", row=3, value=1)
        self.pages(page.page, page.total, page.page_size)


class LinkView(CoreView):
    def __init__(self, core, source, page, *, filtering=False):
        super().__init__(core, source.route, source.timezone)
        self.record = getattr(source, "record", None)
        self.filtering, self.link_page = filtering, page.page
        self.button("Back", "refresh")
        self.button("Refresh", "link_refresh")
        options = [
            discord.SelectOption(
                label="Không lọc dự án" if filtering else "Không gắn liên kết", value="none"
            )
        ]
        options += [
            discord.SelectOption(label=record_label(row)[:100], value=row.id) for row in page.items
        ]
        self.select("link", options, row=1, placeholder="Chọn dự án / công việc…")
        self.pages(page.page, page.total, page.page_size, row=2, action="link_page")


class ConfirmationView(CoreView):
    def __init__(self, core, route, timezone, intent, request, pages, page=0):
        super().__init__(core, route, timezone)
        self.intent, self.request, self.text_pages, self.confirm_page = intent, request, pages, page
        remaining = max(0.1, (request.expires_at - datetime.now(UTC)).total_seconds())
        self.timeout = min(300, remaining)
        self.expires_at = monotonic() + self.timeout
        self.button("Bỏ qua", "reject", style=discord.ButtonStyle.danger)
        self.button(
            "Duyệt", "approve", disabled=page != len(pages) - 1, style=discord.ButtonStyle.success
        )
        self.pages(page, len(pages), 1, row=1, action="confirm_page")


class CoreErrorView(CoreView):
    def __init__(self, core, route, timezone, *, draft=None, intent=None, token=None):
        super().__init__(core, route, timezone)
        self.draft, self.intent, self.approved_token = draft, intent, token
        self.button("Back", "back")
        self.button("Refresh", "refresh")
        if draft is not None:
            self.button("Nhập lại", "retry_form")
        if intent is not None:
            self.button("Thử lại", "retry_write")
        if route.screen in (Screen.TASKS, Screen.CALENDAR) and route.item_id is None:
            self.button("Chọn ngày", "date")
