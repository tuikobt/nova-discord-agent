import discord
from discord import app_commands

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.error_handlers import send_private
from app.discord_bot.renderers.dashboard import render_dashboard
from app.domain.authorization import OwnerAuthorization


class FoundationCommands:
    def __init__(self, authorization: OwnerAuthorization) -> None:
        self.authorization = authorization

    async def ping(self, interaction: discord.Interaction) -> None:
        # Check here as well: callbacks remain guarded when invoked directly.
        if not await authorize_interaction(interaction, self.authorization):
            return
        await send_private(interaction, "Pong! NOVA đang online.")

    async def menu(self, interaction: discord.Interaction) -> None:
        if not await authorize_interaction(interaction, self.authorization):
            return
        # P1 has no DB work in commands, so acknowledge immediately.
        await interaction.response.send_message(
            embed=render_dashboard(),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def register(self, tree: app_commands.CommandTree) -> None:
        tree.add_command(
            app_commands.Command(
                name="ping", description="Kiểm tra trạng thái NOVA", callback=self.ping
            )
        )
        tree.add_command(
            app_commands.Command(name="menu", description="Mở dashboard NOVA", callback=self.menu)
        )
