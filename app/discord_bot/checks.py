import logging

import discord
from discord import app_commands

from app.discord_bot.error_handlers import DENIED_MESSAGE, handle_command_error, send_private
from app.domain.authorization import OwnerAuthorization

logger = logging.getLogger(__name__)


async def authorize_interaction(
    interaction: discord.Interaction, authorization: OwnerAuthorization
) -> bool:
    if authorization.is_owner(interaction.user.id):
        return True
    logger.warning("owner_access_denied", extra={"interaction_id": interaction.id})
    await send_private(interaction, DENIED_MESSAGE)
    return False


class OwnerCommandTree(app_commands.CommandTree):
    def __init__(self, client: discord.Client, authorization: OwnerAuthorization) -> None:
        super().__init__(client)
        self.authorization = authorization

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await authorize_interaction(interaction, self.authorization)

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_command_error(interaction, error)
