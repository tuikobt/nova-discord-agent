"""Owner-only Discord orchestration. All personal panels are ephemeral."""

import logging

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.core_controller import CoreController
from app.discord_bot.core_state import CORE_SCREENS, CoreRoute
from app.discord_bot.dashboard_publisher import DashboardPublisher, DashboardPublishError
from app.discord_bot.error_handlers import send_private
from app.discord_bot.renderers.dashboard import (
    render_dashboard,
    render_error,
    render_help,
    render_module,
    render_settings,
)
from app.discord_bot.views.dashboard import DashboardView, OwnerView, PanelView
from app.domain.authorization import OwnerAuthorization
from app.domain.modules import Screen
from app.services.dashboard_service import DashboardService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class DashboardController:
    def __init__(
        self,
        client: discord.Client,
        authorization: OwnerAuthorization,
        settings: SettingsService,
        core_services,
    ) -> None:
        self.client = client
        self.authorization = authorization
        self.settings = settings
        self.service = DashboardService(settings, core_services.summary)
        self.publisher = DashboardPublisher(client, settings)
        self.core = CoreController(self, core_services)

    async def restore(self) -> None:
        preferences = await self.settings.get(self.authorization.owner_id)
        location = preferences.dashboard
        self.client.add_view(
            DashboardView(self), message_id=location.message_id if location else None
        )

    async def finish(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        view: OwnerView,
        previous: OwnerView | None = None,
    ) -> None:
        view.message = await interaction.edit_original_response(
            content=None, embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
        )
        if previous is not None and not previous.anchor:
            previous.stop()

    async def menu(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        if interaction.guild_id is None:
            await self.navigate(interaction, Screen.HOME, new_panel=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.publisher.ensure(
                interaction.user.id, interaction.channel, DashboardView(self)
            )
            content = f"Dashboard NOVA: {result.message.jump_url}"
            if result.pin_warning:
                content += (
                    "\nBảng đã tạo nhưng chưa ghim được. Kiểm tra quyền Pin Messages "
                    "của bot hoặc ghim thủ công, rồi mở lại /menu."
                )
            # Shared anchor stays generic; real aggregates are returned only to the owner.
            view = DashboardView(self, anchor=False)
            view.message = await interaction.edit_original_response(
                content=content,
                embed=render_dashboard(await self.service.overview(interaction.user.id)),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as error:
            await self.show_error(interaction, error)

    async def navigate(
        self,
        interaction: discord.Interaction,
        screen: Screen | str,
        *,
        from_anchor: bool = False,
        new_panel: bool = False,
        page: int = 0,
        previous: OwnerView | None = None,
    ) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        if from_anchor or new_panel:
            await interaction.response.defer(ephemeral=True, thinking=True)
        else:
            await interaction.response.defer()
        route = Screen.HOME
        try:
            route = Screen(screen)
            if from_anchor:
                await self.publisher.require_current(interaction.user.id, interaction)
            if route in CORE_SCREENS:
                await self.core.open(interaction, CoreRoute(route, page=page), previous=previous)
                return
            if route == Screen.HOME:
                embed = render_dashboard(await self.service.overview(interaction.user.id))
                view = DashboardView(self, anchor=False)
            elif route == Screen.HELP:
                embed, view = render_help(), PanelView(self, route)
            elif route == Screen.SETTINGS:
                preferences = await self.settings.get(interaction.user.id)
                embed = render_settings(preferences)
                view = PanelView(self, route, timezone_default=preferences.timezone)
            else:
                embed = render_module(route, self.service.features(route, page))
                if route == Screen.TODAY:
                    overview = await self.service.overview(interaction.user.id)
                    embed.add_field(
                        name="Hôm nay",
                        inline=False,
                        value=f"{overview.today:%d/%m/%Y} • {overview.timezone}",
                    )
                view = PanelView(self, route, page=page)
            await self.finish(interaction, embed, view, previous)
        except Exception as error:
            await self.show_error(interaction, error, route, previous)

    async def refresh_anchor(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.publisher.refresh(interaction.user.id, interaction, DashboardView(self))
            await interaction.edit_original_response(content="Đã làm mới dashboard.")
        except Exception as error:
            await self.show_error(interaction, error)

    async def save_timezone(
        self, interaction: discord.Interaction, timezone: str, *, previous: OwnerView | None = None
    ) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        await interaction.response.defer()
        try:
            await self.settings.update_timezone(interaction.user.id, timezone)
            preferences = await self.settings.get(interaction.user.id)
            await self.finish(
                interaction,
                render_settings(preferences, saved=True),
                PanelView(self, Screen.SETTINGS, timezone_default=preferences.timezone),
                previous,
            )
        except Exception as error:
            await self.show_error(interaction, error, Screen.SETTINGS, previous)

    async def show_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        screen: Screen = Screen.HOME,
        previous: OwnerView | None = None,
    ) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        logger.error(
            "dashboard_interaction_failed",
            extra={"interaction_id": interaction.id, "error_type": type(error).__name__},
        )
        embed = render_error()
        if isinstance(error, DashboardPublishError):
            embed.description = str(error)
        elif isinstance(error, discord.Forbidden):
            embed.description = (
                "NOVA chưa đủ quyền trong kênh. Kiểm tra View Channel, Read Message History, "
                "Send Messages và Embed Links của bot, rồi mở lại /menu. Không cần Administrator."
            )
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            await self.finish(interaction, embed, PanelView(self, screen, error=True), previous)
        except discord.HTTPException:
            await send_private(interaction, "Không thể cập nhật panel. Hãy mở lại /menu.")
