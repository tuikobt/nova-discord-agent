"""Private reminder views and persistent, delivery-bound notification buttons."""

import asyncio
import calendar
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic
from uuid import uuid4

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.error_handlers import send_private
from app.discord_bot.views.dashboard import OwnerView

STATUS = {"active": "Đang chạy", "paused": "Tạm dừng", "done": "Đã gửi", "cancelled": "Đã hủy"}
RECURRENCE = {"none": "Một lần", "daily": "Hằng ngày", "weekly": "Hằng tuần"}


@dataclass
class ReminderDraft:
    timezone: str
    title: str = ""
    fire: datetime | None = None
    recurrence: str = "none"
    weekday: int | None = None
    target: str = "dm"
    channel_id: str | None = None
    task_id: str | None = None
    event_id: str | None = None
    record: object = None
    request_id: str = field(default_factory=lambda: str(uuid4()))
    expires_at: float = field(default_factory=lambda: monotonic() + 600)
    saved: object = None
    raw_time: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class ReminderView(OwnerView):
    def __init__(self, controller, *, kind="list", expires_at=None, **state):
        super().__init__(controller.dashboard)
        self.reminders, self.kind, self.state = controller, kind, state
        self.lock = asyncio.Lock()
        if expires_at is not None:
            self.expires_at = min(self.expires_at, expires_at)
            self.timeout = max(0.1, self.expires_at - monotonic())

    async def guard(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if self.is_finished():
            await send_private(interaction, "Màn hình đã đổi; mở lại từ Reminders hoặc Refresh.")
            return False
        return True

    async def interaction_check(self, interaction):
        return await self.guard(interaction)

    async def on_error(self, interaction, error, item):
        await self.reminders.error(interaction, error, self)

    def button(self, label, action, *, value=None, row=0, disabled=False):
        self.add_item(ReminderButton(label, action, value, row=row, disabled=disabled))

    def select(self, action, options, *, row, placeholder):
        if options:
            self.add_item(ReminderSelect(action, options, row=row, placeholder=placeholder))


class ReminderButton(discord.ui.Button):
    def __init__(self, label, action, value, **kwargs):
        super().__init__(
            label=label, custom_id=f"nova:reminders:v1:{action}:{uuid4().hex[:8]}", **kwargs
        )
        self.action, self.value = action, value

    async def callback(self, interaction):
        if await self.view.guard(interaction):
            await self.view.reminders.dispatch(interaction, self.view, self.action, self.value)


class ReminderSelect(discord.ui.Select):
    def __init__(self, action, options, **kwargs):
        super().__init__(options=options, custom_id=f"nova:reminders:v1:{action}", **kwargs)
        self.action = action

    async def callback(self, interaction):
        if not await self.view.guard(interaction):
            return
        if len(self.values) != 1 or self.values[0] not in {item.value for item in self.options}:
            await send_private(interaction, "Lựa chọn không hợp lệ; hãy Refresh.")
            return
        await self.view.reminders.dispatch(interaction, self.view, self.action, self.values[0])


class ListView(ReminderView):
    def __init__(self, controller, page, status):
        super().__init__(controller, page=page.page, status=status)
        self.button("Thêm", "create")
        self.button("Cài đặt gửi", "settings")
        self.button("Back", "home")
        self.button("Refresh", "list")
        self.select(
            "filter",
            [discord.SelectOption(label="Tất cả", value="all", default=status is None)]
            + [
                discord.SelectOption(label=label, value=value, default=status == value)
                for value, label in STATUS.items()
            ],
            row=1,
            placeholder="Lọc trạng thái…",
        )
        self.select(
            "detail",
            [discord.SelectOption(label=row.title[:100], value=row.id) for row in page.items],
            row=2,
            placeholder="Chọn lời nhắc…",
        )
        self.button("Previous", "page", value=page.page - 1, row=3, disabled=page.page == 0)
        self.button(
            "Next", "page", value=page.page + 1, row=3, disabled=(page.page + 1) * 5 >= page.total
        )


class DetailView(ReminderView):
    def __init__(self, controller, record):
        super().__init__(controller, kind="detail", record=record)
        self.button("Back", "list")
        self.button("Refresh", "detail", value=record.id)
        self.button("Sửa", "edit", disabled=record.status in ("done", "cancelled"))
        self.button(
            "Tiếp tục" if record.status == "paused" else "Tạm dừng",
            "status",
            value="active" if record.status == "paused" else "paused",
            row=1,
            disabled=record.status in ("done", "cancelled"),
        )
        self.button(
            "Hủy", "status", value="cancelled", row=1, disabled=record.status == "cancelled"
        )


class DraftView(ReminderView):
    def __init__(self, controller, draft, preferences):
        super().__init__(controller, kind="draft", expires_at=draft.expires_at, draft=draft)
        self.button("Lưu", "save")
        self.button("Chọn ngày/giờ", "date")
        self.button("Sửa nội dung", "text")
        self.button("Bỏ bản nháp", "list")
        self.select(
            "recurrence",
            [
                discord.SelectOption(label=label, value=value, default=draft.recurrence == value)
                for value, label in RECURRENCE.items()
            ],
            row=1,
            placeholder="Loại lời nhắc…",
        )
        if draft.recurrence == "weekly":
            self.select(
                "weekday",
                [
                    discord.SelectOption(
                        label=(f"Thứ {day + 2}" if day < 6 else "Chủ nhật"),
                        value=str(day),
                        default=draft.weekday == day,
                    )
                    for day in range(7)
                ],
                row=2,
                placeholder="Chọn ngày trong tuần…",
            )
        targets = [discord.SelectOption(label="DM", value="dm", default=draft.target == "dm")]
        if preferences.channel_id:
            targets.append(
                discord.SelectOption(
                    label="Kênh riêng đã duyệt", value="channel", default=draft.target == "channel"
                )
            )
        self.select("target", targets, row=3, placeholder="Vị trí gửi…")
        self.button("Gắn task", "links", value="task_id", row=4)
        self.button("Gắn event", "links", value="event_id", row=4)


class DateView(ReminderView):
    def __init__(self, controller, draft, selected):
        super().__init__(
            controller, kind="date", expires_at=draft.expires_at, draft=draft, selected=selected
        )
        month = (selected.year - 1) * 12 + selected.month - 1
        self.button("‹ Tháng", "month", value=-1, disabled=month == 0)
        self.button("Tháng ›", "month", value=1, disabled=month == 119987)
        self.button("Hôm nay", "today")
        self.button("Dùng ngày giờ", "date_apply")
        self.button("Quay lại", "draft")
        last = calendar.monthrange(selected.year, selected.month)[1]
        for row, start, end in ((1, 1, 16), (2, 17, last)):
            self.select(
                "day",
                [
                    discord.SelectOption(
                        label=f"Ngày {n:02d}", value=str(n), default=selected.day == n
                    )
                    for n in range(start, end + 1)
                ],
                row=row,
                placeholder="Chọn ngày…",
            )
        self.select(
            "hour",
            [
                discord.SelectOption(label=f"{n:02d} giờ", value=str(n), default=selected.hour == n)
                for n in range(24)
            ],
            row=3,
            placeholder="Chọn giờ…",
        )
        minutes = sorted(set(range(0, 60, 5)) | {selected.minute})
        self.select(
            "minute",
            [
                discord.SelectOption(
                    label=f"{n:02d} phút", value=str(n), default=selected.minute == n
                )
                for n in minutes
            ],
            row=4,
            placeholder="Chọn phút…",
        )


class LinkView(ReminderView):
    def __init__(self, controller, draft, field_name, page):
        super().__init__(
            controller,
            kind="links",
            expires_at=draft.expires_at,
            draft=draft,
            field_name=field_name,
            page=page.page,
        )
        self.select(
            "link",
            [
                discord.SelectOption(label=(getattr(row, "title", ""))[:100], value=row.id)
                for row in page.items
            ],
            row=0,
            placeholder="Chọn mục liên kết…",
        )
        self.button("Bỏ liên kết", "link", value="none", row=1)
        self.button("Quay lại", "draft", row=1)
        self.button("Previous", "link_page", value=page.page - 1, row=1, disabled=page.page == 0)
        self.button(
            "Next",
            "link_page",
            value=page.page + 1,
            row=1,
            disabled=(page.page + 1) * 5 >= page.total,
        )


class ConfirmationView(ReminderView):
    def __init__(self, controller, request, kind):
        remaining = (request.expires_at - controller.service.now()).total_seconds()
        super().__init__(
            controller,
            kind="confirm",
            expires_at=monotonic() + max(0, remaining),
            request=request,
            mutation=kind,
            saved=False,
        )
        self.button("Duyệt", "approve")
        self.button("Bỏ qua", "reject")


class SettingsView(ReminderView):
    def __init__(self, controller, preferences):
        super().__init__(controller, kind="settings", preferences=preferences)
        self.button("Bật DM" if not preferences.dm_enabled else "Tắt DM", "dm")
        self.button("Giờ yên lặng", "quiet")
        self.button("Bỏ kênh dự phòng", "clear_channel")
        self.button("Back", "list")
        self.button("Refresh", "settings")
        self.add_item(ChannelSelect())


class ChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Chọn kênh riêng dự phòng…",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction):
        if await self.view.guard(interaction):
            if len(self.values) != 1:
                await send_private(interaction, "Chỉ chọn một kênh riêng.")
                return
            await self.view.reminders.dispatch(
                interaction, self.view, "channel", str(self.values[0].id)
            )


class ReminderModal(discord.ui.Modal):
    def __init__(self, controller, previous, draft):
        super().__init__(title="Nội dung lời nhắc", timeout=300)
        self.reminders, self.previous, self.draft = controller, previous, draft
        self.expires_at = min(monotonic() + 300, draft.expires_at)
        self.title_input = discord.ui.TextInput(
            label="Tiêu đề", default=draft.title, max_length=250
        )
        from app.domain.time import zone

        local = (
            draft.fire.astimezone(zone(draft.timezone)).strftime("%Y-%m-%d %H:%M")
            if draft.fire
            else ""
        )
        self.original_time = local
        self.time_input = discord.ui.TextInput(
            label="Giờ chính xác (tùy chọn)",
            default=draft.raw_time if draft.raw_time is not None else local,
            placeholder="YYYY-MM-DD HH:MM",
            required=False,
            max_length=16,
        )
        self.add_item(self.title_input)
        self.add_item(self.time_input)

    async def interaction_check(self, interaction):
        if not await self.previous.guard(interaction):
            return False
        if monotonic() >= self.expires_at:
            await send_private(interaction, "Form đã hết hạn; mở lại từ Reminders.")
            return False
        return True

    async def on_submit(self, interaction):
        await self.reminders.submit_modal(interaction, self)

    async def on_error(self, interaction, error):
        await self.reminders.error(interaction, error, self.previous, draft=self.draft)


class QuietModal(discord.ui.Modal):
    def __init__(self, controller, previous):
        super().__init__(title="Giờ yên lặng theo timezone Settings", timeout=300)
        self.reminders, self.previous = controller, previous
        self.expires_at = min(monotonic() + 300, previous.expires_at)
        preferences = previous.state["preferences"]
        self.start = discord.ui.TextInput(
            label="Từ HH:MM (trống để tắt)",
            required=False,
            default=preferences.quiet_start.strftime("%H:%M") if preferences.quiet_start else "",
            max_length=5,
        )
        self.end = discord.ui.TextInput(
            label="Đến HH:MM",
            required=False,
            default=preferences.quiet_end.strftime("%H:%M") if preferences.quiet_end else "",
            max_length=5,
        )
        self.add_item(self.start)
        self.add_item(self.end)

    async def interaction_check(self, interaction):
        if not await self.previous.guard(interaction):
            return False
        if monotonic() >= self.expires_at:
            await send_private(interaction, "Form đã hết hạn; mở lại Cài đặt gửi.")
            return False
        return True

    async def on_submit(self, interaction):
        await self.reminders.submit_quiet(interaction, self)

    async def on_error(self, interaction, error):
        await self.reminders.error(interaction, error, self.previous)


class NotificationButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"nova:reminder:v1:(?P<action>done|snooze|cancel):(?P<delivery>[0-9a-f-]{36})",
):
    def __init__(self, action, delivery_id, *, disabled=False):
        self.action, self.delivery_id = action, delivery_id
        label = {"done": "Đã làm", "snooze": "Hoãn 15 phút", "cancel": "Tắt"}[action]
        super().__init__(
            discord.ui.Button(
                label=label, disabled=disabled, custom_id=f"nova:reminder:v1:{action}:{delivery_id}"
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], match["delivery"])

    async def callback(self, interaction):
        controller = interaction.client.dashboard.reminders
        if await authorize_interaction(interaction, controller.service.authorization):
            await controller.notification(interaction, self.delivery_id, self.action)


class NotificationView(discord.ui.View):
    def __init__(self, delivery_id, *, disabled=False):
        super().__init__(timeout=None)
        for action in ("done", "snooze", "cancel"):
            self.add_item(NotificationButton(action, delivery_id, disabled=disabled))
