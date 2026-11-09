"""Discord orchestration only: no SQL, business overlap rules or automatic approvals."""

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.core_state import CORE_SCREENS, CoreRoute, WriteIntent
from app.discord_bot.error_handlers import send_private
from app.discord_bot.form_controller import PICKER_VIEWS, FormController
from app.discord_bot.renderers.core import (
    confirmation_pages,
    render_confirmation,
    render_detail,
    render_list,
    render_today,
)
from app.discord_bot.views.core import (
    ConfirmationView,
    CoreErrorView,
    CorePanelView,
    CoreView,
    LinkView,
)
from app.discord_bot.views.core_forms import CoreFormModal, FormDraft
from app.domain.core import (
    EventData,
    EventRecord,
    ProjectData,
    ProjectRecord,
    TaskData,
    TaskRecord,
    to_record,
)
from app.domain.errors import ConfirmationRequired, DomainError, StorageError, ValidationError
from app.domain.modules import Screen
from app.domain.time import DEFAULT_TIMEZONE, zone

logger = logging.getLogger(__name__)
DATA_TYPES = {Screen.PROJECTS: ProjectData, Screen.TASKS: TaskData, Screen.CALENDAR: EventData}


class CoreController:
    def __init__(self, dashboard, services):
        self.dashboard, self.services = dashboard, services
        self.authorization = dashboard.authorization
        self.settings = dashboard.settings
        self.forms = FormController(self)

    def service(self, screen):
        return {
            Screen.PROJECTS: self.services.projects,
            Screen.TASKS: self.services.tasks,
            Screen.CALENDAR: self.services.calendar,
        }[screen]

    async def ack(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

    async def present(self, interaction, embed, view, previous, *, notice=None):
        if previous is not None and not previous.anchor and previous.is_finished():
            view.stop()
            await send_private(interaction, notice or "Màn hình đã đổi. Hãy Refresh panel đang mở.")
            return
        if notice:
            embed.description = notice + "\n\n" + (embed.description or "")
        await self.dashboard.finish(interaction, embed, view, previous)

    async def link_name(self, actor, record):
        if isinstance(record, TaskRecord) and record.project_id:
            return (await self.services.projects.get(actor, record.project_id)).name
        if isinstance(record, EventRecord) and record.task_id:
            return (await self.services.tasks.get(actor, record.task_id)).title
        return None

    async def open(self, interaction, route, *, previous=None, notice=None):
        if not await authorize_interaction(interaction, self.authorization):
            return
        if isinstance(previous, CoreView) and not await previous.guard(interaction):
            if notice:
                await send_private(interaction, notice + " Mở lại module để xem kết quả.")
            return
        await self.ack(interaction)
        try:
            if route.screen not in CORE_SCREENS:
                raise ValidationError("Module không hợp lệ.")
            preferences = await self.settings.get(interaction.user.id)
            timezone = preferences.timezone
            day = route.day or datetime.now(UTC).astimezone(zone(timezone)).date()
            route = replace(route, day=day)
            actor = interaction.user.id
            if route.screen == Screen.TODAY:
                events = await self.services.calendar.list_day(
                    actor, day, timezone=timezone, status="confirmed", page_size=5
                )
                tasks, total = await self.services.summary.today_tasks(actor, day, timezone)
                embed = render_today(day, timezone, events, tasks, total)
                view = CorePanelView(self, route, timezone, today_records=events.items + tasks)
            elif route.item_id:
                record = await self.service(route.screen).get(actor, route.item_id)
                progress = (
                    await self.services.projects.progress(actor, record.id)
                    if route.screen == Screen.PROJECTS
                    else None
                )
                embed = render_detail(
                    route.screen,
                    record,
                    timezone,
                    progress=progress,
                    link_name=await self.link_name(actor, record),
                )
                view = CorePanelView(self, route, timezone, record=record)
            else:
                page = await self.fetch_page(actor, route, timezone)
                last = max(0, (page.total - 1) // page.page_size)
                if route.page > last:
                    route = replace(route, page=last)
                    page = await self.fetch_page(actor, route, timezone)
                progress = (
                    {
                        row.id: await self.services.projects.progress(actor, row.id)
                        for row in page.items
                    }
                    if route.screen == Screen.PROJECTS
                    else None
                )
                project_name = (
                    (await self.services.projects.get(actor, route.project_id)).name
                    if route.project_id
                    else None
                )
                embed = render_list(
                    route, page, timezone, progress=progress, project_name=project_name
                )
                view = CorePanelView(self, route, timezone, page=page)
            await self.present(interaction, embed, view, previous, notice=notice)
        except Exception as error:
            await self.error(interaction, error, route, previous, notice=notice)

    async def fetch_page(self, actor, route, timezone):
        common = {"status": route.status, "page": route.page, "page_size": 5}
        if route.screen == Screen.TASKS:
            return await self.services.tasks.list(
                actor,
                priority=route.priority,
                project_id=route.project_id,
                due_from=route.due_from,
                due_until=route.due_until,
                **common,
            )
        if route.screen == Screen.PROJECTS:
            return await self.services.projects.list(actor, **common)
        method = (
            self.services.calendar.list_week if route.weekly else self.services.calendar.list_day
        )
        return await method(actor, route.day, timezone=timezone, **common)

    async def error(
        self,
        interaction,
        error,
        route,
        previous=None,
        *,
        draft=None,
        intent=None,
        token=None,
        notice=None,
    ):
        if not await authorize_interaction(interaction, self.authorization):
            return
        await self.ack(interaction)
        logger.error(
            "core_interaction_failed",
            extra={"interaction_id": interaction.id, "error_type": type(error).__name__},
        )
        message = (
            str(error)
            if isinstance(error, DomainError)
            else "Chưa thể xử lý. Hãy thử lại hoặc mở lại module."
        )
        embed = discord.Embed(
            title="NOVA — Chưa thể xử lý", description=message, colour=discord.Colour.orange()
        )
        timezone = getattr(previous, "timezone", DEFAULT_TIMEZONE)
        view = CoreErrorView(
            self,
            route,
            timezone,
            draft=draft,
            intent=intent if isinstance(error, StorageError) else None,
            token=token,
        )
        try:
            await self.present(interaction, embed, view, previous, notice=notice)
        except discord.HTTPException:
            view.stop()
            await send_private(
                interaction, notice or "Không cập nhật được panel. Hãy mở lại /menu."
            )

    async def submit_form(self, interaction, modal):
        await self.forms.submit(interaction, modal)

    async def confirm(self, interaction, intent, request, previous):
        timezone = previous.timezone
        names = {}
        for row in (request.before, request.after):
            for attr, service, label in (
                ("project_id", self.services.projects, "name"),
                ("task_id", self.services.tasks, "title"),
            ):
                key = getattr(row, attr, None)
                if key and key not in names:
                    names[key] = getattr(await service.get(interaction.user.id, key), label)
        pages = confirmation_pages(request, timezone, names)
        view = ConfirmationView(self, intent.route, timezone, intent, request, pages)
        await self.present(interaction, render_confirmation(request, pages, 0), view, previous)

    async def commit(self, interaction, intent, previous, *, token=None):
        if not await authorize_interaction(interaction, self.authorization):
            return
        if not await previous.guard(interaction):
            return
        await self.ack(interaction)
        async with intent.lock:
            if intent.cancelled:
                await send_private(interaction, "Đã bỏ qua thay đổi này.")
                return
            if intent.saved is not None:
                await send_private(interaction, "Dữ liệu đã được lưu. Dùng Refresh để xem lại.")
                return
            service = self.service(intent.route.screen)
            try:
                if intent.record is None:
                    saved = await service.create(
                        interaction.user.id,
                        intent.data,
                        request_id=intent.request_id,
                        approval_token=token,
                    )
                else:
                    expected = (
                        intent.record.updated_at
                        if isinstance(intent.record, ProjectRecord)
                        else intent.record.version
                    )
                    saved = await service.update(
                        interaction.user.id,
                        intent.record.id,
                        intent.data,
                        expected=expected,
                        approval_token=token,
                    )
                intent.saved = (
                    saved  # service already committed; never re-submit after rendering failure
                )
            except ConfirmationRequired as pending:
                try:
                    await self.confirm(interaction, intent, pending.request, previous)
                except Exception as error:
                    await self.error(interaction, error, intent.route, previous)
                return
            except Exception as error:
                await self.error(
                    interaction, error, intent.route, previous, intent=intent, token=token
                )
                return
            detail = replace(
                intent.route,
                item_id=saved.id,
                parent=intent.route.parent if intent.route.item_id else intent.route,
            )
            if intent.record is None and isinstance(saved, EventRecord):
                parent = replace(
                    intent.route, day=saved.starts_at.astimezone(zone(previous.timezone)).date()
                )
                detail = replace(detail, day=parent.day, parent=parent)
            await self.open(
                interaction, detail, previous=previous, notice="Đã lưu thay đổi vào database."
            )

    async def pick_link(self, interaction, source, *, page=0, filtering=False):
        if not await authorize_interaction(interaction, self.authorization):
            return
        if not await source.guard(interaction):
            return
        await self.ack(interaction)
        service = (
            self.services.projects
            if filtering or source.route.screen == Screen.TASKS
            else self.services.tasks
        )
        data = await service.list(interaction.user.id, page=page, page_size=5)
        view = LinkView(self, source, data, filtering=filtering)
        embed = discord.Embed(
            title="NOVA — Chọn dự án"
            if service is self.services.projects
            else "NOVA — Chọn công việc",
            description=(
                f"{data.total} bản ghi • Trang {page + 1}. Chọn trong menu; không cần nhập ID."
            ),
            colour=discord.Colour.blurple(),
        )
        await self.present(interaction, embed, view, source)

    async def dispatch(self, interaction, view, action, value=None):
        if not await view.guard(interaction):
            return
        if isinstance(view, PICKER_VIEWS):
            await self.forms.dispatch(interaction, view, action, value)
            return
        route = view.route
        try:
            if action in ("edit", "add", "new_task", "new_event", "retry_form"):
                if action == "retry_form":
                    draft = view.draft
                else:
                    screen = (
                        Screen.TASKS
                        if action == "new_task"
                        else Screen.CALENDAR
                        if action == "new_event"
                        else route.screen
                    )
                    record = view.record if action == "edit" else None
                    target = (
                        route
                        if screen == route.screen
                        else CoreRoute(screen, day=route.day, parent=route)
                    )
                    link_id = (
                        (
                            view.record.id
                            if isinstance(getattr(view, "record", None), ProjectRecord)
                            else route.project_id
                        )
                        if screen == Screen.TASKS
                        else view.record.id
                        if screen == Screen.CALENDAR
                        and isinstance(getattr(view, "record", None), TaskRecord)
                        else None
                    )
                    seed = (
                        view.record.title
                        if screen == Screen.CALENDAR
                        and isinstance(getattr(view, "record", None), TaskRecord)
                        else ""
                    )
                    if screen == Screen.TASKS and isinstance(
                        getattr(view, "record", None), ProjectRecord
                    ):
                        target = replace(target, project_id=view.record.id)
                    draft = FormDraft(
                        target,
                        view.timezone,
                        record=record,
                        link_id=link_id,
                        seed_title=seed,
                        expires_at=view.expires_at,
                    )
                await interaction.response.send_modal(
                    CoreFormModal(
                        self, view, draft, advanced=action == "retry_form" and draft.advanced_input
                    )
                )
            elif action == "date":
                await self.forms.open_date(interaction, view)
            elif action == "back":
                if route.parent:
                    await self.open(interaction, route.parent, previous=view)
                else:
                    await self.dashboard.navigate(interaction, Screen.HOME, previous=view)
            elif action == "refresh":
                await self.open(interaction, route, previous=view)
            elif action == "record":
                screen, key = value.split(":", 1)
                await self.open(
                    interaction,
                    CoreRoute(Screen(screen), item_id=key, day=route.day, parent=route),
                    previous=view,
                )
            elif action in (
                "filter_status",
                "filter_priority",
                "page",
                "week",
                "shift",
                "today_calendar",
                "today_tasks",
                "project_tasks",
            ):
                if action == "filter_status":
                    target = replace(route, status=None if value == "all" else value, page=0)
                elif action == "filter_priority":
                    target = replace(route, priority=None if value == "all" else value, page=0)
                elif action == "page":
                    target = replace(route, page=value)
                elif action == "week":
                    target = replace(route, weekly=not route.weekly, page=0)
                elif action == "shift":
                    target = replace(
                        route,
                        day=route.day + timedelta(days=value * (7 if route.weekly else 1)),
                        page=0,
                    )
                elif action == "project_tasks":
                    target = CoreRoute(Screen.TASKS, project_id=view.record.id, parent=route)
                else:
                    target = CoreRoute(
                        Screen.CALENDAR if action == "today_calendar" else Screen.TASKS,
                        day=route.day,
                        parent=route,
                    )
                await self.open(interaction, target, previous=view)
            elif action in ("status", "priority", "fixed", "task_done"):
                data = to_record(DATA_TYPES[route.screen], view.record)
                if action == "task_done":
                    data = replace(
                        data,
                        status="todo" if view.record.status in ("done", "cancelled") else "done",
                    )
                elif action == "fixed":
                    if value not in ("yes", "no"):
                        raise ValidationError("Loại lịch không hợp lệ.")
                    data = replace(data, is_fixed=value == "yes")
                else:
                    data = replace(data, **{action: value})
                await self.commit(interaction, WriteIntent(route, data, record=view.record), view)
            elif action in ("pick_link", "filter_project", "link_page", "link_refresh"):
                await self.pick_link(
                    interaction,
                    view,
                    page=value
                    if action == "link_page"
                    else view.link_page
                    if action == "link_refresh"
                    else 0,
                    filtering=action == "filter_project" or getattr(view, "filtering", False),
                )
            elif action == "link":
                key = None if value == "none" else value
                if view.filtering:
                    await self.open(
                        interaction, replace(route, project_id=key, page=0), previous=view
                    )
                else:
                    data = to_record(DATA_TYPES[route.screen], view.record)
                    data = replace(
                        data, **{"project_id" if route.screen == Screen.TASKS else "task_id": key}
                    )
                    await self.commit(
                        interaction, WriteIntent(route, data, record=view.record), view
                    )
            elif action == "confirm_page":
                if type(value) is not int or not 0 <= value < len(view.text_pages):
                    raise ValidationError("Trang xác nhận không hợp lệ.")
                updated = ConfirmationView(
                    self, route, view.timezone, view.intent, view.request, view.text_pages, value
                )
                await self.ack(interaction)
                await self.present(
                    interaction,
                    render_confirmation(view.request, view.text_pages, value),
                    updated,
                    view,
                )
            elif action == "approve":
                if view.confirm_page != len(view.text_pages) - 1:
                    raise ValidationError("Xem hết các trang thay đổi trước khi duyệt.")
                await self.commit(interaction, view.intent, view, token=view.request.token)
            elif action == "reject":
                await self.ack(interaction)
                async with view.intent.lock:
                    if view.intent.saved is not None:
                        await send_private(
                            interaction, "Thay đổi đã lưu; không thể bỏ qua sau khi lưu."
                        )
                        return
                    view.intent.cancelled = True
                    self.service(route.screen).approvals.consume(view.request.token)
                await self.open(
                    interaction, route, previous=view, notice="Đã bỏ qua; không ghi thay đổi."
                )
            elif action == "retry_write":
                await self.commit(interaction, view.intent, view, token=view.approved_token)
            else:
                raise ValidationError("Thao tác không hợp lệ.")
        except Exception as error:
            await self.error(interaction, error, route, view)
