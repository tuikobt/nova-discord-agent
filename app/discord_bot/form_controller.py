"""Private draft orchestration; picker interactions never write database records."""

import calendar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import monotonic

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.error_handlers import send_private
from app.discord_bot.views.core_forms import CoreFormModal, FormDraft, wall_time
from app.discord_bot.views.core_pickers import (
    MINUTES,
    DateChoice,
    DatePickerView,
    DeadlineRange,
    DeadlineRangeView,
    DraftLinkView,
    DraftView,
    render_date_picker,
    render_draft,
    render_range,
)
from app.domain.errors import DomainError, ValidationError
from app.domain.modules import Screen
from app.domain.time import parse_local_datetime, zone

PICKER_VIEWS = (DraftView, DraftLinkView, DeadlineRangeView, DatePickerView)


class FormController:
    def __init__(self, core):
        self.core = core

    async def submit(self, interaction, modal):
        if not await authorize_interaction(interaction, self.core.authorization):
            return
        async with modal.submit_lock, modal.draft.lock:
            if not await modal.previous.guard(interaction):
                return
            if monotonic() >= min(modal.expires_at, modal.draft.expires_at):
                await send_private(interaction, "Bản nháp/form đã hết hạn. Mở lại từ module.")
                return
            if modal.submitted:
                await send_private(interaction, "Đã nhận nội dung. Tiếp tục trong bản nháp.")
                return
            await self.core.ack(interaction)
            try:
                modal.draft.raw.update({key: item.value for key, item in modal.inputs.items()})
                modal.draft.validate_text()
                # Exact input stays strict; empty dates can still be selected in the picker.
                for key in modal.inputs:
                    value = modal.draft.raw[key].strip()
                    if key.endswith("_at") and value:
                        if not (modal.draft.record and value == modal.draft.defaults()[key]):
                            parse_local_datetime(value, modal.draft.timezone)
                await self.show_draft(interaction, modal.draft, modal.previous)
                modal.submitted = True
            except Exception as error:
                await self.core.error(
                    interaction, error, modal.draft.route, modal.previous, draft=modal.draft
                )

    async def show_draft(self, interaction, draft, previous, notice=None):
        await self.core.ack(interaction)
        screen = draft.route.screen
        link_name = None
        if screen != Screen.PROJECTS:
            field = "project_id" if screen == Screen.TASKS else "task_id"
            key = draft.selections.get(field, getattr(draft.record, field, draft.link_id))
            if key:
                service = (
                    self.core.services.projects
                    if screen == Screen.TASKS
                    else self.core.services.tasks
                )
                row = await service.get(interaction.user.id, key)
                link_name = row.name if screen == Screen.TASKS else row.title
        await self.core.present(
            interaction,
            render_draft(draft, link_name=link_name, notice=notice),
            DraftView(self.core, draft),
            previous,
        )

    async def show_range(self, interaction, state, previous, notice=None):
        await self.core.ack(interaction)
        await self.core.present(
            interaction, render_range(state, notice), DeadlineRangeView(self.core, state), previous
        )

    async def show_picker(self, interaction, state, previous, notice=None):
        await self.core.ack(interaction)
        await self.core.present(
            interaction,
            render_date_picker(state, notice),
            DatePickerView(self.core, state),
            previous,
        )

    def picker_state(self, view, target, field, *, date_only=False):
        local = datetime.now(UTC).astimezone(zone(view.timezone)).replace(tzinfo=None)
        # The initial selection is a labelled suggestion, never written until Apply/Save.
        seed = datetime.combine(view.route.day or local.date(), local.time()).replace(
            minute=0, second=0, microsecond=0
        )
        if isinstance(target, FormDraft):
            value = target.values()[field]
            if value:
                seed = datetime.strptime(value, "%Y-%m-%d %H:%M")
            elif field == "ends_at" and target.values()["starts_at"]:
                seed = datetime.strptime(
                    target.values()["starts_at"], "%Y-%m-%d %H:%M"
                ) + timedelta(hours=1)
        elif isinstance(target, DeadlineRange):
            value = getattr(target, field)
            if value:
                seed = datetime.combine(value, datetime.min.time())
        return DateChoice(
            view.route, view.timezone, target, field, seed, view.expires_at, date_only
        )

    async def open_date(self, interaction, view):
        if not await view.guard(interaction):
            return
        route = view.route
        if route.screen == Screen.CALENDAR:
            state = self.picker_state(view, route, "day", date_only=True)
            await self.show_picker(interaction, state, view)
        else:

            def day(value):
                return value.astimezone(zone(view.timezone)).date() if value else None

            state = DeadlineRange(
                route,
                view.timezone,
                day(route.due_from),
                day(route.due_until) - timedelta(days=1) if route.due_until else None,
                view.expires_at,
            )
            await self.show_range(interaction, state, view)

    async def return_from_picker(self, interaction, view, *, apply=False):
        state = view.state
        target = state.target
        if isinstance(target, FormDraft):
            if apply:
                value = state.selected.isoformat(sep=" ", timespec="minutes")
                if not (target.record and value == target.defaults()[state.field]):
                    parse_local_datetime(value, state.timezone)
                target.raw[state.field] = value
            await self.show_draft(interaction, target, view)
        elif isinstance(target, DeadlineRange):
            if apply:
                target = replace(target, **{state.field: state.selected.date()})
            await self.show_range(interaction, target, view)
        else:
            route = replace(target, day=state.selected.date(), page=0) if apply else target
            await self.core.open(interaction, route, previous=view)

    async def links(self, interaction, view, page=0):
        await self.core.ack(interaction)
        service = (
            self.core.services.projects
            if view.route.screen == Screen.TASKS
            else self.core.services.tasks
        )
        data = await service.list(interaction.user.id, page=page, page_size=5)
        embed = discord.Embed(
            title="NOVA — Chọn liên kết cho bản nháp",
            description=f"{data.total} mục • Trang {page + 1} • Chưa ghi database.",
            colour=discord.Colour.blurple(),
        )
        await self.core.present(
            interaction, embed, DraftLinkView(self.core, view.draft, data), view
        )

    async def dispatch(self, interaction, view, action, value=None):
        if not await view.guard(interaction):
            return
        draft = getattr(view, "draft", None)
        if isinstance(view, DatePickerView) and isinstance(view.state.target, FormDraft):
            draft = view.state.target
        if draft is not None:
            async with draft.lock:
                await self._dispatch(interaction, view, action, value)
        else:
            await self._dispatch(interaction, view, action, value)

    async def _dispatch(self, interaction, view, action, value):
        if not await view.guard(interaction):
            return
        try:
            if isinstance(view, DatePickerView):
                await self.date_action(interaction, view, action, value)
            elif isinstance(view, DeadlineRangeView):
                await self.range_action(interaction, view, action, value)
            elif action in ("draft_link", "draft_link_page"):
                await self.links(interaction, view, value if action == "draft_link_page" else 0)
            elif action == "draft_link_back":
                await self.show_draft(interaction, view.draft, view)
            elif action == "draft_link_value":
                field = "project_id" if view.route.screen == Screen.TASKS else "task_id"
                view.draft.selections[field] = None if value == "none" else value
                await self.show_draft(interaction, view.draft, view)
            elif action in ("draft_text", "draft_exact"):
                await interaction.response.send_modal(
                    CoreFormModal(self.core, view, view.draft, advanced=action == "draft_exact")
                )
            elif action == "draft_cancel":
                await self.core.open(
                    interaction,
                    view.route,
                    previous=view,
                    notice="Đã bỏ bản nháp; không ghi dữ liệu.",
                )
            elif action == "draft_date":
                await self.show_picker(
                    interaction, self.picker_state(view, view.draft, value), view
                )
            elif action == "draft_save":
                try:
                    if view.draft.intent is None:
                        view.draft.intent = view.draft.parse()
                except ValidationError as error:
                    await self.show_draft(interaction, view.draft, view, notice=str(error))
                    return
                await self.core.commit(interaction, view.draft.intent, view)
            else:
                draft = view.draft
                if action == "draft_clear":
                    draft.raw[value] = ""
                elif action == "draft_priority":
                    draft.selections["priority"] = value
                elif action == "draft_status":
                    draft.selections["status"] = value
                elif action == "draft_fixed":
                    if value not in ("yes", "no"):
                        raise ValidationError("Loại lịch không hợp lệ.")
                    draft.selections["is_fixed"] = value == "yes"
                elif action == "draft_estimate":
                    draft.raw["estimated_minutes"] = "" if value == "none" else value
                elif action == "draft_duration":
                    if value not in {str(n) for n in MINUTES}:
                        raise ValidationError("Thời lượng không hợp lệ.")
                    start = draft.values()["starts_at"]
                    if not start:
                        await self.show_draft(
                            interaction,
                            draft,
                            view,
                            notice="Chọn bắt đầu trước, sau đó chọn thời lượng.",
                        )
                        return
                    end = parse_local_datetime(start, draft.timezone) + timedelta(
                        minutes=int(value)
                    )
                    draft.raw["ends_at"] = wall_time(end, draft.timezone)
                else:
                    raise ValidationError("Thao tác bản nháp không hợp lệ.")
                await self.show_draft(interaction, draft, view)
        except Exception as error:
            if isinstance(error, DomainError) and isinstance(view, DatePickerView):
                await self.show_picker(interaction, view.state, view, notice=str(error))
            elif isinstance(error, DomainError) and isinstance(view, DeadlineRangeView):
                await self.show_range(interaction, view.state, view, notice=str(error))
            else:
                await self.core.error(
                    interaction, error, view.route, view, draft=getattr(view, "draft", None)
                )

    async def date_action(self, interaction, view, action, value):
        state, selected = view.state, view.state.selected
        if action == "picker_apply":
            await self.return_from_picker(interaction, view, apply=True)
            return
        if action == "picker_cancel":
            await self.return_from_picker(interaction, view)
            return
        if action == "picker_month":
            if value not in (-1, 1):
                raise ValidationError("Tháng không hợp lệ.")
            index = (selected.year - 1) * 12 + selected.month - 1 + value
            if not 0 <= index < 9999 * 12:
                raise ValidationError("Năm nằm ngoài phạm vi hỗ trợ.")
            year, month = index // 12 + 1, index % 12 + 1
            selected = selected.replace(
                year=year, month=month, day=min(selected.day, calendar.monthrange(year, month)[1])
            )
        elif action in ("picker_today", "picker_tomorrow"):
            day = datetime.now(UTC).astimezone(zone(state.timezone)).date()
            if action == "picker_tomorrow":
                day += timedelta(days=1)
            selected = selected.replace(year=day.year, month=day.month, day=day.day)
        elif action in ("picker_day", "picker_day_late", "picker_hour", "picker_minute"):
            component = "day" if action == "picker_day_late" else action.removeprefix("picker_")
            allowed = (
                range(1, calendar.monthrange(selected.year, selected.month)[1] + 1)
                if component == "day"
                else range(24)
                if component == "hour"
                else {*range(0, 60, 5), selected.minute}
            )
            if value not in {str(n) for n in allowed} or (state.date_only and component != "day"):
                raise ValidationError("Lựa chọn ngày/giờ không hợp lệ.")
            selected = selected.replace(**{component: int(value)})
        else:
            raise ValidationError("Thao tác chọn ngày không hợp lệ.")
        await self.show_picker(interaction, replace(state, selected=selected), view)

    async def range_action(self, interaction, view, action, value):
        state = view.state
        if action == "range_cancel":
            await self.core.open(interaction, state.route, previous=view)
            return
        if action == "range_date":
            if value not in ("start", "end"):
                raise ValidationError("Mốc ngày không hợp lệ.")
            await self.show_picker(
                interaction, self.picker_state(view, state, value, date_only=True), view
            )
            return
        if action == "range_clear":
            if value not in ("start", "end"):
                raise ValidationError("Mốc ngày không hợp lệ.")
            state = replace(state, **{value: None})
        elif action in ("range_today", "range_week"):
            start = datetime.now(UTC).astimezone(zone(state.timezone)).date()
            state = replace(
                state, start=start, end=start + timedelta(days=6 if action == "range_week" else 0)
            )
        elif action == "range_apply":
            if state.start and state.end and state.start > state.end:
                raise ValidationError("Từ ngày phải trước hoặc bằng đến ngày.")

            def midnight(day):
                return (
                    parse_local_datetime(f"{day:%Y-%m-%d} 00:00", state.timezone) if day else None
                )

            route = replace(
                state.route,
                due_from=midnight(state.start),
                due_until=midnight(state.end + timedelta(days=1)) if state.end else None,
                page=0,
            )
            await self.core.open(interaction, route, previous=view)
            return
        else:
            raise ValidationError("Thao tác lọc ngày không hợp lệ.")
        await self.show_range(interaction, state, view)
