"""Opt-in reports use owner DM or an explicitly approved private channel."""

import discord

from app.discord_bot.personal_controller import report_text
from app.discord_bot.views.personal import ReportButton
from app.domain.errors import ValidationError
from app.domain.reminder_delivery import DeliveryFailure


class DiscordReportSender:
    def __init__(self, client, private_sender):
        self.client, self.private_sender = client, private_sender
        self.authorization = client.authorization

    def available(self):
        return self.client.is_ready()

    async def send(self, actor, key, payload, routing):
        self.authorization.require_owner(actor)
        policy = routing["policy"]
        view = discord.ui.View(timeout=None)
        view.add_item(ReportButton(key))
        text = report_text(payload)
        kwargs = dict(
            embed=discord.Embed(title="NOVA — Báo cáo", description=text[:3500]),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        try:
            if policy["target"] == "dm":
                if not routing["dm_enabled"]:
                    # Disabling DM is not consent to reroute its private contents.
                    raise DeliveryFailure("forbidden", permanent=True)
                try:
                    owner = self.client.get_user(actor) or await self.client.fetch_user(actor)
                    message = await owner.send(**kwargs)
                    return str(message.id), str(message.channel.id)
                except discord.Forbidden:
                    if not policy["fallback"]:
                        raise DeliveryFailure("forbidden", permanent=True) from None
            channel = await self.private_sender.validate_channel(actor, policy["channel_id"])
            message = await channel.send(**kwargs)
            return str(message.id), str(message.channel.id)
        except DeliveryFailure:
            raise
        except (discord.Forbidden, discord.NotFound, ValidationError):
            raise DeliveryFailure("forbidden", permanent=True) from None
        except discord.HTTPException:
            raise DeliveryFailure("http_error") from None
        except (TimeoutError, OSError):
            raise DeliveryFailure("network_error") from None
