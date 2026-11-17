"""Discord-only transport: owner DM or a configured, strictly private text channel."""

import discord

from app.discord_bot.renderers.core import safe
from app.domain.errors import ValidationError
from app.domain.reminder_delivery import DeliveryFailure
from app.domain.time import format_local_datetime


class DiscordReminderSender:
    def __init__(self, client, authorization):
        self.client, self.authorization = client, authorization

    def available(self):
        return self.client.is_ready()

    async def validate_channel(self, actor_id, channel_id):
        self.authorization.require_owner(actor_id)
        channel = await self.client.fetch_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            raise ValidationError("Chỉ dùng kênh văn bản riêng, không dùng thread/forum.")
        guild = channel.guild
        if guild.owner_id != actor_id:
            raise ValidationError("Kênh gửi phải nằm trong server riêng do owner sở hữu.")
        bot_id = self.client.user.id
        if channel.permissions_for(guild.default_role).view_channel:
            raise ValidationError("Kênh đang cho @everyone xem; không thể gửi dữ liệu riêng tư.")
        for role in guild.roles:
            own_bot_role = role.tags is not None and role.tags.bot_id == bot_id
            if not own_bot_role and channel.permissions_for(role).view_channel:
                raise ValidationError("Kênh còn role khác có quyền xem, kể cả Administrator.")
        for target, overwrite in channel.overwrites.items():
            if overwrite.view_channel is True and not (
                isinstance(target, discord.Member) and target.id in (actor_id, bot_id)
            ):
                # Own bot's managed role is the only safe role exception.
                if not (
                    isinstance(target, discord.Role)
                    and target.tags is not None
                    and target.tags.bot_id == bot_id
                ):
                    raise ValidationError("Kênh có quyền xem cho thành viên/role chưa được phép.")
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            raise ValidationError("Bot thiếu quyền xem/gửi tin nhắn hoặc Embed Links trong kênh.")
        return channel

    async def send(self, claim):
        actor = self.authorization.owner_id
        self.authorization.require_owner(actor)
        if claim.reminder.owner_id != str(actor):
            raise DeliveryFailure("forbidden", permanent=True)
        from app.discord_bot.views.reminders import NotificationView

        embed = discord.Embed(
            title="NOVA — Nhắc nhở",
            description=safe(claim.reminder.title, 1000),
            colour=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Thời điểm dự kiến",
            value=format_local_datetime(
                claim.delivery.scheduled_fire_at, claim.preferences.timezone
            ),
            inline=False,
        )
        embed.add_field(
            name="Loại",
            value=(
                "Hoãn 15 phút"
                if claim.delivery.delivery_kind == "snooze"
                else {"none": "Một lần", "daily": "Hằng ngày", "weekly": "Hằng tuần"}[
                    claim.reminder.recurrence_type
                ]
            ),
        )
        embed.set_footer(text="Nút có hiệu lực 24 giờ • Hoãn chỉ lần này • Tắt cần Duyệt")
        kwargs = {
            "embed": embed,
            "view": NotificationView(claim.delivery.id),
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        try:
            if claim.reminder.delivery_target == "dm" and claim.preferences.dm_enabled:
                try:
                    user = self.client.get_user(actor) or await self.client.fetch_user(actor)
                    message = await user.send(**kwargs)
                    return str(message.id)
                except discord.Forbidden:
                    # Only a forbidden DM may use the approved private fallback.
                    pass
            channel_id = claim.preferences.channel_id
            if channel_id is None or (
                claim.reminder.delivery_target == "channel"
                and claim.reminder.channel_id != channel_id
            ):
                raise DeliveryFailure("forbidden", permanent=True)
            channel = await self.validate_channel(actor, channel_id)
            message = await channel.send(**kwargs)
            return str(message.id)
        except DeliveryFailure:
            raise
        except (discord.Forbidden, discord.NotFound, ValidationError):
            raise DeliveryFailure("forbidden", permanent=True) from None
        except discord.HTTPException:
            raise DeliveryFailure("http_error") from None
        except (TimeoutError, OSError):
            raise DeliveryFailure("network_error") from None
