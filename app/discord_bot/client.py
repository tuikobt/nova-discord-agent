import logging
import sys

import discord

from app.config import Settings
from app.db.session import Database
from app.discord_bot.checks import OwnerCommandTree
from app.discord_bot.commands.foundation import FoundationCommands
from app.domain.authorization import OwnerAuthorization
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class NovaClient(discord.Client):
    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.dm_messages = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.database = database
        self.authorization = OwnerAuthorization(settings.owner_id)
        self.tree = OwnerCommandTree(self, self.authorization)
        self.foundation = FoundationCommands(self.authorization)
        self.foundation.register(self.tree)
        self.settings_service = SettingsService(database.sessions, self.authorization)

    async def setup_hook(self) -> None:
        await self.database.initialize()
        await self.settings_service.initialize_owner(self.settings.owner_id, self.settings.timezone)
        if self.settings.guild_id is not None:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            commands = await self.tree.sync(guild=guild)
        else:
            commands = await self.tree.sync()
        logger.info("slash_commands_registered", extra={"command_count": len(commands)})

    async def on_ready(self) -> None:
        logger.info("bot_online")

    async def on_disconnect(self) -> None:
        logger.warning("gateway_disconnected")

    async def on_resumed(self) -> None:
        logger.info("gateway_resumed")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return
        if not self.authorization.is_owner(message.author.id):
            return
        # No reading, logging, or persisting message.content in Foundation.
        try:
            await message.channel.send(
                "NOVA đang ở Phase 1. Dùng /menu trong server để mở dashboard. "
                "AI Assistant: Sắp ra mắt.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            logger.warning("dm_response_failed", extra={"error_type": type(error).__name__})

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        # Never log args/kwargs or the default traceback containing message content.
        error_type = sys.exc_info()[0]
        logger.error(
            "discord_event_failed",
            extra={"error_type": error_type.__name__ if error_type else "UnknownError"},
        )

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await self.database.close()
