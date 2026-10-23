import discord
from discord import app_commands

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.dashboard_controller import DashboardController
from app.discord_bot.error_handlers import send_private
from app.domain.authorization import OwnerAuthorization
from app.domain.modules import Screen


class FoundationCommands:
    def __init__(self, authorization: OwnerAuthorization, dashboard: DashboardController) -> None:
        self.authorization = authorization
        self.dashboard = dashboard

    async def ping(self, interaction: discord.Interaction) -> None:
        # Check here as well: callbacks remain guarded when invoked directly.
        if not await authorize_interaction(interaction, self.authorization):
            return
        await send_private(interaction, "Pong! NOVA đang online.")

    async def menu(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        await self.dashboard.menu(interaction)

    async def help(self, interaction: discord.Interaction) -> None:
        if await authorize_interaction(interaction, self.authorization):
            await self.dashboard.navigate(interaction, Screen.HELP, new_panel=True)

    async def settings(self, interaction: discord.Interaction) -> None:
        if await authorize_interaction(interaction, self.authorization):
            await self.dashboard.navigate(interaction, Screen.SETTINGS, new_panel=True)

    def register(self, tree: app_commands.CommandTree) -> None:
        tree.add_command(
            app_commands.Command(
                name="ping", description="Kiểm tra trạng thái NOVA", callback=self.ping
            )
        )
        tree.add_command(
            app_commands.Command(name="menu", description="Mở dashboard NOVA", callback=self.menu)
        )
        tree.add_command(
            app_commands.Command(
                name="help", description="Hướng dẫn sử dụng NOVA", callback=self.help
            )
        )
        tree.add_command(
            app_commands.Command(
                name="settings", description="Cài đặt NOVA", callback=self.settings
            )
        )
