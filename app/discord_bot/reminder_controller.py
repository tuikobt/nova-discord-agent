"""Private reminder UI orchestration. Business rules live in ReminderService."""

import calendar
import logging
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from time import monotonic
from types import SimpleNamespace

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.error_handlers import send_private
from app.discord_bot.renderers.core import safe
from app.discord_bot.renderers.reminders import (
    RECURRENCE,
    STATUS,
    panel,
    render_confirmation,
    render_detail,
    render_draft,
    render_list,
    render_settings,
    when,
)
from app.discord_bot.views.reminders import (
    ConfirmationView,
    DateView,
    DetailView,
    DraftView,
    LinkView,
    ListView,
    NotificationView,
    QuietModal,
    ReminderDraft,
    ReminderModal,
    ReminderView,
    SettingsView,
)
from app.domain.core import text_value
from app.domain.errors import ConfirmationRequired, DomainError, ValidationError
from app.domain.modules import Screen
from app.domain.reminder_delivery import NotificationPreferences
from app.domain.reminders import RecurrenceRule, ReminderData
from app.domain.time import parse_local_datetime, zone

logger = logging.getLogger(__name__)


class ReminderController:
    def __init__(self, dashboard, service):
        self.dashboard, self.service = dashboard, service

    async def ack(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

    async def present(self, interaction, embed, view, previous=None, notice=None):
        if notice:
            embed.description = notice + "\n\n" + (embed.description or "")
        if previous is not None and not previous.anchor and previous.is_finished():
            view.stop()
            await send_private(interaction, notice or "Màn hình đã đổi; mở lại Reminders.")
            return
        await self.dashboard.finish(interaction, embed, view, previous)

    async def links(self, actor, data):
        labels = {}
        for key, label, service in (
            (data.task_id, "Công việc", self.dashboard.core.services.tasks),
            (data.event_id, "Sự kiện", self.dashboard.core.services.calendar),
        ):
            labels[label] = safe((await service.get(actor, key)).title, 250) if key else "Không gắn"
        return labels

    async def open(self, interaction, *, page=0, status=None, key=None, previous=None, notice=None):
        if not await authorize_interaction(interaction, self.service.authorization):
            return
        await self.ack(interaction)
        try:
            actor = interaction.user.id
            preferences = await self.service.preferences(actor)
            if key:
                record = await self.service.get(actor, key)
                history = await self.service.history(actor, key)
                labels = await self.links(actor, record)
                embed = render_detail(
                    record,
                    preferences.timezone,
                    history,
                    "\n".join(f"{name}: {value}" for name, value in labels.items()),
                )
                view = DetailView(self, record)
            else:
                records = await self.service.list(actor, status=status, page=page)
                if page and not records.items and records.total:
                    records = await self.service.list(
                        actor, status=status, page=(records.total - 1) // 5
                    )
                embed, view = (
                    render_list(records, preferences.timezone),
                    ListView(self, records, status),
                )
            view.state["preferences"] = preferences
            await self.present(interaction, embed, view, previous, notice)
        except Exception as error:
            await self.error(interaction, error, previous)

    async def draft(self, interaction, draft, previous):
        preferences = await self.service.preferences(interaction.user.id)
        labels = await self.links(interaction.user.id, draft)
        await self.present(
            interaction,
            render_draft(draft, "\n".join(f"{k}: {v}" for k, v in labels.items())),
            DraftView(self, draft, preferences),
            previous,
        )

    async def settings(self, interaction, previous=None, notice=None):
        if not await authorize_interaction(interaction, self.service.authorization):
            return
        await self.ack(interaction)
        preferences = await self.service.preferences(interaction.user.id)
        await self.present(
            interaction,
            render_settings(preferences),
            SettingsView(self, preferences),
            previous,
            notice,
        )

    async def describe(self, actor, data):
        if isinstance(data, NotificationPreferences):
            return {
                "DM": "Bật" if data.dm_enabled else "Tắt",
                "Kênh": f"<#{data.channel_id}>" if data.channel_id else "Không dùng",
                "Giờ yên lặng": (
                    f"{data.quiet_start:%H:%M} → {data.quiet_end:%H:%M}"
                    if data.quiet_start and data.quiet_end
                    else "Tắt"
                ),
            }
        return {
            "Tiêu đề": safe(data.title),
            "Thời điểm": when(
                data.next_fire_at,
                data.recurrence.timezone
                if data.recurrence
                else (await self.service.preferences(actor)).timezone,
            ),
            "Trạng thái": STATUS[data.status],
            "Lặp": RECURRENCE[data.recurrence_type]
            + (
                f" • {data.recurrence.time} ({data.recurrence.timezone})"
                + (
                    f" • Thứ {data.recurrence.weekday + 2}"
                    if data.recurrence.weekday is not None and data.recurrence.weekday < 6
                    else " • Chủ nhật"
                    if data.recurrence.weekday == 6
                    else ""
                )
                if data.recurrence
                else ""
            ),
            "Gửi tới": "DM" if data.delivery_target == "dm" else f"<#{data.channel_id}>",
            **await self.links(actor, data),
        }

    async def confirm(self, interaction, request, kind, previous):
        before = await self.describe(interaction.user.id, request.before)
        after = await self.describe(interaction.user.id, request.after)
        embed = render_confirmation(before, after)
        embed.description += (
            "\nThay đổi lời nhắc sẽ vô hiệu hóa các lần gửi/hoãn chưa xử lý."
            if kind == "update"
            else "\nCài đặt áp dụng cho các lần gửi tiếp theo."
        )
        await self.present(
            interaction,
            embed,
            ConfirmationView(self, request, kind),
            previous,
        )

    async def submit_modal(self, interaction, modal):
        if not await modal.interaction_check(interaction):
            return
        draft = modal.draft
        async with draft.lock:
            if not await modal.previous.guard(interaction) or draft.saved is not None:
                return
            await self.ack(interaction)
            try:
                draft.title = str(modal.title_input.value)
                draft.raw_time = str(modal.time_input.value)
                text_value(draft.title, 250)
                if draft.raw_time and (draft.fire is None or draft.raw_time != modal.original_time):
                    draft.fire = parse_local_datetime(draft.raw_time, draft.timezone)
                draft.raw_time = None
                await self.draft(interaction, draft, modal.previous)
            except Exception as error:
                await self.error(interaction, error, modal.previous, draft=draft)

    async def submit_quiet(self, interaction, modal):
        if not await modal.interaction_check(interaction):
            return
        await self.ack(interaction)
        try:

            def parse(value):
                if not value:
                    return None
                RecurrenceRule(time=value)
                return time.fromisoformat(value)

            prefs = modal.previous.state["preferences"]
            await self.configure(
                interaction,
                replace(
                    prefs, quiet_start=parse(modal.start.value), quiet_end=parse(modal.end.value)
                ),
                modal.previous,
            )
        except Exception as error:
            await self.error(interaction, error, modal.previous)

    async def configure(self, interaction, preferences, previous, token=None):
        try:
            await self.service.configure(
                interaction.user.id,
                dm_enabled=preferences.dm_enabled,
                channel_id=preferences.channel_id,
                quiet_start=preferences.quiet_start,
                quiet_end=preferences.quiet_end,
                expected=preferences.updated_at,
                approval_token=token,
            )
        except ConfirmationRequired as error:
            await self.confirm(interaction, error.request, "preferences", previous)
        else:
            if previous.kind == "confirm":
                previous.state["saved"] = True
            await self.settings(interaction, previous, "Đã lưu cài đặt gửi.")
        return None

    async def dispatch(self, interaction, view, action, value=None):
        if not await view.guard(interaction):
            return
        try:
            state, actor = view.state, interaction.user.id
            if action in ("create", "edit", "text"):
                draft = state.get("draft")
                if draft is None:
                    record = state.get("record") if action == "edit" else None
                    preferences = state["preferences"]
                    draft = ReminderDraft(
                        timezone=(
                            record.recurrence.timezone
                            if record and record.recurrence
                            else preferences.timezone
                        ),
                        expires_at=view.expires_at,
                    )
                    if record:
                        draft.title, draft.fire, draft.record = (
                            record.title,
                            record.next_fire_at,
                            record,
                        )
                        draft.recurrence = record.recurrence_type
                        draft.weekday = record.recurrence.weekday if record.recurrence else None
                        draft.target, draft.channel_id = record.delivery_target, record.channel_id
                        draft.task_id, draft.event_id = record.task_id, record.event_id
                await interaction.response.send_modal(ReminderModal(self, view, draft))
                return
            if action == "quiet":
                await interaction.response.send_modal(QuietModal(self, view))
                return
            if action == "home":
                await self.dashboard.navigate(interaction, Screen.HOME, previous=view)
                return
            await self.ack(interaction)
            if action in ("list", "page", "filter", "detail"):
                await self.open(
                    interaction,
                    key=value if action == "detail" else None,
                    status=(None if value == "all" else value)
                    if action == "filter"
                    else state.get("status"),
                    page=value
                    if action == "page"
                    else state.get("page", 0)
                    if action == "list"
                    else 0,
                    previous=view,
                )
            elif action == "settings":
                await self.settings(interaction, view)
            elif action in ("dm", "channel", "clear_channel"):
                prefs = state["preferences"]
                after = replace(
                    prefs,
                    **(
                        {"dm_enabled": not prefs.dm_enabled}
                        if action == "dm"
                        else {"channel_id": value if action == "channel" else None}
                    ),
                )
                await self.configure(interaction, after, view)
            elif action == "status":
                record = state["record"]
                try:
                    result = await self.service.set_status(
                        actor, record.id, value, expected=record.updated_at
                    )
                except ConfirmationRequired as error:
                    await self.confirm(interaction, error.request, "update", view)
                else:
                    await self.open(interaction, key=result.id, previous=view)
            elif action in ("approve", "reject"):
                async with view.lock:
                    if view.state["saved"]:
                        await send_private(interaction, "Thay đổi đã được xử lý; hãy Refresh.")
                        return
                    request = state["request"]
                    if action == "reject":
                        self.service.approvals.consume(request.token)
                        state["saved"] = True
                        await self.open(
                            interaction, previous=view, notice="Đã bỏ qua; không ghi thay đổi."
                        )
                    elif state["mutation"] == "preferences":
                        await self.configure(interaction, request.after, view, request.token)
                    else:
                        result = await self.service.update(
                            actor,
                            request.before.id,
                            request.after,
                            expected=request.before.updated_at,
                            approval_token=request.token,
                        )
                        state["saved"] = True
                        await self.open(
                            interaction, key=result.id, previous=view, notice="Đã lưu thay đổi."
                        )
            elif "draft" in state:
                async with state["draft"].lock:
                    if not await view.guard(interaction):
                        return
                    await self.draft_action(interaction, view, action, value)
            else:
                raise ValidationError("Thao tác không hợp lệ; hãy Refresh.")
        except Exception as error:
            await self.error(interaction, error, view)

    async def draft_action(self, interaction, view, action, value):
        state, actor, draft = view.state, interaction.user.id, view.state["draft"]
        if monotonic() >= draft.expires_at:
            raise ValidationError("Bản nháp đã hết hạn; mở lại Reminders.")
        if draft.saved is not None:
            await self.open(
                interaction, key=draft.saved.id, previous=view, notice="Dữ liệu đã lưu."
            )
            return
        if action == "save":
            if draft.fire is None:
                raise ValidationError("Chọn ngày/giờ trước khi Lưu.")
            rule = (
                RecurrenceRule(
                    time=draft.fire.astimezone(zone(draft.timezone)).strftime("%H:%M"),
                    timezone=draft.timezone,
                    weekday=draft.weekday if draft.recurrence == "weekly" else None,
                )
                if draft.recurrence != "none"
                else None
            )
            data = ReminderData(
                title=draft.title,
                next_fire_at=draft.fire,
                recurrence_type=draft.recurrence,
                recurrence=rule,
                delivery_target=draft.target,
                channel_id=draft.channel_id,
                task_id=draft.task_id,
                event_id=draft.event_id,
                status=draft.record.status if draft.record else "active",
            )
            try:
                if draft.record:
                    result = await self.service.update(
                        actor, draft.record.id, data, expected=draft.record.updated_at
                    )
                else:
                    result = await self.service.create(actor, data, request_id=draft.request_id)
            except ConfirmationRequired as error:
                await self.confirm(interaction, error.request, "update", view)
            else:
                draft.saved = result
                await self.open(
                    interaction, key=result.id, previous=view, notice="Đã lưu lời nhắc."
                )
        elif action == "date":
            local = (draft.fire or self.service.now() + timedelta(minutes=2)).astimezone(
                zone(draft.timezone)
            )
            await self.show_date(interaction, draft, local.replace(tzinfo=None), view)
        elif action in ("month", "day", "hour", "minute", "today"):
            selected = state["selected"]
            if action == "month":
                index = (selected.year - 1) * 12 + selected.month - 1 + value
                if not 0 <= index < 119988:
                    raise ValidationError("Tháng nằm ngoài phạm vi hỗ trợ.")
                year, month = index // 12 + 1, index % 12 + 1
                selected = selected.replace(
                    year=year,
                    month=month,
                    day=min(selected.day, calendar.monthrange(year, month)[1]),
                )
            elif action == "today":
                day = self.service.now().astimezone(zone(draft.timezone)).date()
                selected = datetime.combine(day, selected.time())
            else:
                selected = selected.replace(**{action: int(value)})
            await self.show_date(interaction, draft, selected, view)
        elif action == "date_apply":
            draft.fire = parse_local_datetime(
                state["selected"].strftime("%Y-%m-%d %H:%M"), draft.timezone
            )
            draft.raw_time = None
            await self.draft(interaction, draft, view)
        elif action in ("recurrence", "weekday", "target", "draft"):
            if action == "recurrence":
                draft.recurrence = value
                if value == "weekly" and draft.weekday is None and draft.fire:
                    draft.weekday = draft.fire.astimezone(zone(draft.timezone)).weekday()
            elif action == "weekday":
                draft.weekday = int(value)
            elif action == "target":
                prefs = await self.service.preferences(actor)
                draft.target, draft.channel_id = (
                    value,
                    prefs.channel_id if value == "channel" else None,
                )
            await self.draft(interaction, draft, view)
        elif action in ("links", "link_page"):
            field = value if action == "links" else state["field_name"]
            page = 0 if action == "links" else value
            services = self.dashboard.core.services
            records = (
                await services.tasks.list(actor, page=page, page_size=5)
                if field == "task_id"
                else await services.calendar.list(
                    actor,
                    datetime.min.replace(tzinfo=UTC),
                    datetime.max.replace(tzinfo=UTC),
                    page=page,
                    page_size=5,
                )
            )
            await self.present(
                interaction,
                panel("Chọn liên kết", "Chọn mục của bạn, hoặc Bỏ liên kết."),
                LinkView(self, draft, field, records),
                view,
            )
        elif action == "link":
            setattr(draft, state["field_name"], None if value == "none" else value)
            await self.draft(interaction, draft, view)
        else:
            raise ValidationError("Thao tác bản nháp không hợp lệ.")

    async def show_date(self, interaction, draft, selected, previous):
        grid = calendar.TextCalendar(firstweekday=0).formatmonth(selected.year, selected.month)
        embed = panel(
            "Chọn ngày/giờ lời nhắc",
            f"```\n{grid}```\n{selected:%Y-%m-%d %H:%M} • {draft.timezone}\n"
            "Chọn xong bấm Dùng ngày giờ. Bản nháp chưa ghi DB.",
        )
        await self.present(interaction, embed, DateView(self, draft, selected), previous)

    async def notification(self, interaction, delivery_id, action):
        if not await authorize_interaction(interaction, self.service.authorization):
            return
        await self.ack(interaction)
        try:
            if action == "cancel":
                record = await self.service.notification_reminder(
                    interaction.user.id, delivery_id, interaction.message.id
                )
                try:
                    await self.service.set_status(
                        interaction.user.id, record.id, "cancelled", expected=record.updated_at
                    )
                except ConfirmationRequired as error:
                    await self.confirm(interaction, error.request, "update", None)
                else:
                    await self.open(interaction, key=record.id, notice="Lời nhắc đã hủy.")
            else:
                record = await self.service.notification_action(
                    interaction.user.id, delivery_id, interaction.message.id, action
                )
                try:
                    await interaction.message.edit(
                        view=NotificationView(delivery_id, disabled=True)
                    )
                except discord.HTTPException:
                    pass
                await self.open(
                    interaction,
                    key=record.id,
                    notice="Đã hoãn 15 phút." if action == "snooze" else "Đã ghi nhận hoàn thành.",
                )
        except Exception as error:
            await self.error(interaction, error)

    async def error(self, interaction, error, previous=None, *, draft=None):
        if not await authorize_interaction(interaction, self.service.authorization):
            return
        await self.ack(interaction)
        logger.error(
            "reminder_interaction_failed",
            extra={"error_type": type(error).__name__, "interaction_id": interaction.id},
        )
        message = (
            str(error)
            if isinstance(error, DomainError)
            else "Chưa thể xử lý; hãy Refresh hoặc thử lại."
        )
        saved = (
            (previous is not None and previous.state.get("saved"))
            or (draft is not None and draft.saved is not None)
            or (
                previous is not None
                and previous.state.get("draft") is not None
                and previous.state["draft"].saved is not None
            )
        )
        if saved:
            message = "Thay đổi đã lưu. Mở lại Reminders hoặc Refresh để xem dữ liệu."
        try:
            draft = draft or (previous.state.get("draft") if previous is not None else None)
            if draft is not None and monotonic() < draft.expires_at:
                # Keep retry controls even if the failing operation was a DB read.
                prefs = SimpleNamespace(channel_id=draft.channel_id)
                view = DraftView(self, draft, prefs)
            else:
                view = ReminderView(self)
                view.button("Back", "list")
                view.button("Refresh", "list")
            await self.present(interaction, panel("Chưa hoàn tất", message), view, previous)
        except discord.HTTPException:
            await send_private(interaction, "Panel đã hết hạn. Mở lại Reminders từ /menu.")
