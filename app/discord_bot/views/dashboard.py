from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.error_handlers import send_private
from app.domain.modules import MODULES, MORE_SCREENS, QUICK_SCREENS, Screen
from app.domain.schemas import paginate

if TYPE_CHECKING:
    from app.discord_bot.dashboard_controller import DashboardController

logger = logging.getLogger(__name__)
LABELS = {
    Screen.TODAY: "Today",
    Screen.TASKS: "Tasks",
    Screen.PROJECTS: "Projects",
    Screen.REMINDERS: "Reminders",
    Screen.AI: "AI Assistant",
}


class OwnerView(discord.ui.View):
    def __init__(self, controller: DashboardController, *, anchor: bool = False) -> None:
        super().__init__(timeout=None if anchor else 600)
        self.controller = controller
        self.anchor = anchor
        self.expires_at = monotonic() + 600
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await authorize_interaction(interaction, self.controller.authorization):
            return False
        if not self.anchor:
            remaining = self.expires_at - monotonic()
            if remaining <= 0:
                await send_private(
                    interaction, "Panel đã hết hạn. Hãy mở lại từ dashboard hoặc /menu."
                )
                return False
            # Keep timeout before the ephemeral token expires even if a modal
            # is opened without replacing this panel's message/token.
            self.timeout = remaining
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        await self.controller.show_error(interaction, error)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content="Phiên đã hết hạn. Bấm nút trên bảng neo hoặc mở /menu để tiếp tục.",
                    view=self,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as error:
                logger.warning(
                    "panel_expiration_failed", extra={"error_type": type(error).__name__}
                )


class NavigateButton(discord.ui.Button):
    def __init__(
        self,
        controller: DashboardController,
        screen: Screen,
        *,
        label: str,
        row: int,
        anchor: bool = False,
        page: int = 0,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"nova:dashboard:v1:{screen.value}:{label.lower().replace(' ', '_')}",
            disabled=disabled,
        )
        self.controller = controller
        self.screen = screen
        self.anchor = anchor
        self.page = page

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.controller.navigate(
            interaction, self.screen, from_anchor=self.anchor, page=self.page, previous=self.view
        )


class MoreSelect(discord.ui.Select):
    def __init__(self, controller: DashboardController, *, anchor: bool) -> None:
        super().__init__(
            placeholder="Các module khác…",
            row=2,
            custom_id="nova:dashboard:v1:modules",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=MODULES[screen].title, value=screen.value, description="Sắp ra mắt"
                )
                for screen in MORE_SCREENS
            ],
        )
        self.controller = controller
        self.anchor = anchor

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.controller.authorization):
            return
        if len(self.values) != 1 or self.values[0] not in MORE_SCREENS:
            await send_private(interaction, "Module không hợp lệ. Hãy mở lại /menu.")
            return
        await self.controller.navigate(
            interaction, Screen(self.values[0]), from_anchor=self.anchor, previous=self.view
        )


class AnchorRefresh(discord.ui.Button):
    def __init__(self, controller: DashboardController) -> None:
        super().__init__(label="Refresh", row=3, custom_id="nova:dashboard:v1:refresh")
        self.controller = controller

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.controller.refresh_anchor(interaction)


class DashboardView(OwnerView):
    def __init__(self, controller: DashboardController, *, anchor: bool = True) -> None:
        super().__init__(controller, anchor=anchor)
        for index, screen in enumerate(QUICK_SCREENS):
            self.add_item(
                NavigateButton(
                    controller, screen, label=LABELS[screen], row=index // 3, anchor=anchor
                )
            )
        self.add_item(MoreSelect(controller, anchor=anchor))
        for screen in (Screen.HELP, Screen.SETTINGS):
            self.add_item(
                NavigateButton(controller, screen, label=screen.value.title(), row=3, anchor=anchor)
            )
        if anchor:
            self.add_item(AnchorRefresh(controller))
        else:
            self.add_item(NavigateButton(controller, Screen.HOME, label="Refresh", row=3))


class EditTimezoneButton(discord.ui.Button):
    def __init__(self, controller: DashboardController) -> None:
        super().__init__(label="Sửa Timezone", row=1, custom_id="nova:settings:v1:timezone")
        self.controller = controller

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.controller.authorization):
            return
        if self.view.is_finished() or monotonic() >= self.view.expires_at:
            await send_private(interaction, "Panel đã hết hạn; hãy mở lại Settings.")
            return
        await interaction.response.send_modal(
            TimezoneModal(self.controller, self.view.timezone_default, self.view)
        )


class PanelView(OwnerView):
    def __init__(
        self,
        controller: DashboardController,
        screen: Screen,
        *,
        page: int = 0,
        timezone_default: str = "Asia/Ho_Chi_Minh",
        error: bool = False,
    ) -> None:
        super().__init__(controller)
        self.timezone_default = timezone_default
        self.add_item(NavigateButton(controller, Screen.HOME, label="Back", row=0))
        self.add_item(NavigateButton(controller, screen, label="Refresh", row=0, page=page))
        for target in (Screen.HELP, Screen.SETTINGS):
            if target != screen:
                self.add_item(NavigateButton(controller, target, label=target.value.title(), row=0))
        if screen == Screen.SETTINGS and not error:
            self.add_item(EditTimezoneButton(controller))
        elif screen in MODULES and screen != Screen.SETTINGS and not error:
            pages = paginate(MODULES[screen].features, page)
            if pages.total > 1:
                self.add_item(
                    NavigateButton(
                        controller,
                        screen,
                        label="Previous",
                        row=1,
                        page=max(0, page - 1),
                        disabled=page == 0,
                    )
                )
                self.add_item(
                    NavigateButton(
                        controller,
                        screen,
                        label="Next",
                        row=1,
                        page=min(pages.total - 1, page + 1),
                        disabled=page == pages.total - 1,
                    )
                )


class TimezoneModal(discord.ui.Modal):
    def __init__(self, controller: DashboardController, timezone: str, previous: OwnerView) -> None:
        super().__init__(
            title="Đổi múi giờ", timeout=300, custom_id="nova:settings:v1:timezone_form"
        )
        self.controller = controller
        self.previous = previous
        self.expires_at = monotonic() + 300
        self.timezone_input = discord.ui.TextInput(
            label="Timezone (IANA)",
            default=timezone,
            placeholder="Asia/Ho_Chi_Minh",
            min_length=1,
            max_length=64,
        )
        self.add_item(self.timezone_input)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await authorize_interaction(interaction, self.controller.authorization)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.controller.authorization):
            return
        if monotonic() >= self.expires_at:
            await send_private(interaction, "Biểu mẫu hết hạn. Mở lại Settings để sửa múi giờ.")
            return
        timezone = self.timezone_input.value.strip()
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            await send_private(
                interaction, "Timezone không hợp lệ. Ví dụ: Asia/Ho_Chi_Minh hoặc UTC."
            )
            return
        await self.controller.save_timezone(interaction, timezone, previous=self.previous)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await self.controller.show_error(interaction, error, Screen.SETTINGS)
