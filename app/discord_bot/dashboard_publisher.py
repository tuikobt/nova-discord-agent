"""Discord anchor lifecycle; a single-process lock prevents duplicate /menu sends."""

import asyncio
import logging
from dataclasses import dataclass

import discord

from app.discord_bot.renderers.dashboard import ANCHOR_MARKER, TITLE, render_dashboard
from app.domain.schemas import DashboardLocation
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class DashboardPublishError(RuntimeError):
    """Only application-authored, safe messages may be shown to the owner."""


@dataclass(frozen=True, slots=True)
class PublishedDashboard:
    message: discord.Message
    pin_warning: bool


class DashboardPublisher:
    def __init__(self, client: discord.Client, settings: SettingsService) -> None:
        self.client = client
        self.settings = settings
        self._lock = asyncio.Lock()
        self._pending: discord.Message | None = None

    @staticmethod
    def validate_channel(channel: discord.abc.GuildChannel) -> None:
        if not isinstance(channel, discord.TextChannel):
            raise DashboardPublishError("Hãy mở /menu trong một kênh văn bản riêng của server.")
        if channel.permissions_for(channel.guild.default_role).view_channel:
            raise DashboardPublishError(
                "Hãy dùng kênh riêng cho owner và NOVA: tắt View Channel của @everyone "
                "và chỉ cấp quyền xem cho owner/bot. Sau đó mở lại /menu."
            )

    def is_anchor(self, message: discord.Message) -> bool:
        return bool(
            self.client.user
            and message.author.id == self.client.user.id
            and message.embeds
            and message.embeds[0].title == TITLE
            and message.embeds[0].footer.text == ANCHOR_MARKER
        )

    async def ensure(
        self, actor_id: int, current_channel: discord.abc.GuildChannel, view: discord.ui.View
    ) -> PublishedDashboard:
        self.settings.authorization.require_owner(actor_id)
        async with self._lock:
            preferences = await self.settings.get(actor_id)
            location = preferences.dashboard
            channel = current_channel
            message = None
            if location:
                try:
                    channel = self.client.get_channel(location.channel_id)
                    if channel is None:
                        channel = await self.client.fetch_channel(location.channel_id)
                except discord.NotFound:
                    channel = current_channel
                else:
                    self.validate_channel(channel)
                    try:
                        message = await channel.fetch_message(location.message_id)
                    except discord.NotFound:
                        pass
            self.validate_channel(channel)
            if message is not None and not self.is_anchor(message):
                raise DashboardPublishError(
                    "Tin nhắn đã lưu không phải dashboard NOVA; kiểm tra cấu hình."
                )
            if message is None and self._pending is not None:
                if self._pending.channel.id == channel.id:
                    # Retry a failed DB commit without sending another message.
                    try:
                        message = await channel.fetch_message(self._pending.id)
                    except discord.NotFound:
                        self._pending = None
            if message is None:
                # Recover a send that succeeded just before a process/DB failure.
                async for candidate in channel.history(limit=50):
                    if self.is_anchor(candidate):
                        message = candidate
                        break
            if message is None:
                message = await channel.send(
                    embed=render_dashboard(),
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            self._pending = message
            await self.settings.save_dashboard(actor_id, DashboardLocation(channel.id, message.id))
            self._pending = None
            await message.edit(
                embed=render_dashboard(), view=view, allowed_mentions=discord.AllowedMentions.none()
            )
            pin_warning = False
            if not message.pinned:
                try:
                    await message.pin(reason="NOVA dashboard")
                except discord.HTTPException as error:
                    # The saved anchor still works. A retry must reuse it.
                    logger.warning(
                        "dashboard_pin_failed", extra={"error_type": type(error).__name__}
                    )
                    pin_warning = True
            return PublishedDashboard(message, pin_warning)

    async def require_current(self, actor_id: int, interaction: discord.Interaction) -> None:
        preferences = await self.settings.get(actor_id)
        location = preferences.dashboard
        if (
            location is None
            or interaction.message is None
            or interaction.message.id != location.message_id
            or interaction.channel_id != location.channel_id
        ):
            raise DashboardPublishError(
                "Dashboard này đã cũ. Hãy mở /menu để tới bảng đang sử dụng."
            )

    async def refresh(
        self, actor_id: int, interaction: discord.Interaction, view: discord.ui.View
    ) -> None:
        async with self._lock:
            await self.require_current(actor_id, interaction)
            self.validate_channel(interaction.channel)
            await interaction.message.edit(
                embed=render_dashboard(), view=view, allowed_mentions=discord.AllowedMentions.none()
            )
