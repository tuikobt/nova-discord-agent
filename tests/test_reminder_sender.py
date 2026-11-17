import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import discord
import pytest

from app.discord_bot.reminder_sender import DiscordReminderSender
from app.domain.authorization import AuthorizationError
from app.domain.reminder_delivery import DeliveryFailure, NotificationPreferences

OWNER, BOT = 123456789012345678, 456789012345678901
NOW = datetime(2026, 10, 25, 13, tzinfo=UTC)


def channel_fixture():
    default = Mock(spec=discord.Role)
    default.tags = None
    managed = Mock(spec=discord.Role)
    managed.tags = SimpleNamespace(bot_id=BOT)
    me = Mock(spec=discord.Member)
    me.id = BOT
    owner = Mock(spec=discord.Member)
    owner.id = OWNER
    guild = SimpleNamespace(owner_id=OWNER, default_role=default, roles=[default, managed], me=me)
    channel = Mock(spec=discord.TextChannel)
    channel.guild, channel.id = guild, 234567890123456789
    channel.overwrites = {owner: discord.PermissionOverwrite(view_channel=True)}
    channel.send = AsyncMock(return_value=SimpleNamespace(id=123))
    channel.permissions_for.side_effect = lambda target: SimpleNamespace(
        view_channel=target is me or target is managed, send_messages=True, embed_links=True
    )
    return channel


def fixture(authorization, *, dm=True, fallback=None, target="dm"):
    channel = channel_fixture()
    user = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=123)))
    client = SimpleNamespace(
        user=SimpleNamespace(id=BOT),
        get_user=Mock(return_value=user),
        fetch_user=AsyncMock(return_value=user),
        fetch_channel=AsyncMock(return_value=channel),
        is_ready=Mock(return_value=True),
    )
    claim = SimpleNamespace(
        reminder=SimpleNamespace(
            owner_id=str(OWNER),
            title="@everyone **private**",
            delivery_target=target,
            channel_id=fallback if target == "channel" else None,
            recurrence_type="none",
        ),
        delivery=SimpleNamespace(id=str(uuid4()), scheduled_fire_at=NOW, delivery_kind="scheduled"),
        preferences=NotificationPreferences("Asia/Ho_Chi_Minh", dm, fallback, None, None, NOW),
    )
    return DiscordReminderSender(client, authorization), claim, channel, user


def forbidden():
    return discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "never-log-private-body"
    )


def test_dm_send_uses_only_config_owner_and_suppresses_mentions(authorization):
    async def scenario():
        sender, claim, channel, user = fixture(authorization)
        assert await sender.send(claim) == "123"
        sender.client.get_user.assert_called_once_with(OWNER)
        sender.client.fetch_channel.assert_not_awaited()
        kwargs = user.send.await_args.kwargs
        assert not kwargs["allowed_mentions"].everyone
        assert kwargs["view"].is_persistent()
        assert "13:00" not in str(kwargs["embed"].to_dict())  # Shows 20:00 VN.

    asyncio.run(scenario())


@pytest.mark.parametrize("blocked_dm", [False, True])
def test_only_approved_private_fallback_is_used_when_dm_disabled_or_forbidden(
    authorization, blocked_dm
):
    async def scenario():
        sender, claim, channel, user = fixture(
            authorization, dm=blocked_dm, fallback="234567890123456789"
        )
        user.send.side_effect = forbidden()
        assert await sender.send(claim) == "123"
        channel.send.assert_awaited_once()
        assert user.send.await_count == int(blocked_dm)

    asyncio.run(scenario())


def test_forbidden_dm_without_fallback_is_terminal_and_does_not_try_public_channels(authorization):
    async def scenario():
        sender, claim, channel, user = fixture(authorization)
        user.send.side_effect = forbidden()
        with pytest.raises(DeliveryFailure) as failure:
            await sender.send(claim)
        assert failure.value.permanent and failure.value.code == "forbidden"
        sender.client.fetch_channel.assert_not_awaited()
        channel.send.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("unsafe", ["everyone", "role", "member", "owner", "permissions", "thread"])
def test_channel_send_fails_closed_for_public_roles_members_and_missing_permissions(
    authorization, unsafe
):
    async def scenario():
        sender, claim, channel, user = fixture(
            authorization, dm=False, fallback="234567890123456789"
        )
        if unsafe == "everyone":
            channel.permissions_for.return_value = None
            channel.permissions_for.side_effect = lambda target: SimpleNamespace(
                view_channel=True, send_messages=True, embed_links=True
            )
        elif unsafe == "role":
            role = Mock(spec=discord.Role)
            role.tags = None
            channel.guild.roles.append(role)
            original = channel.permissions_for.side_effect
            channel.permissions_for.side_effect = lambda target: (
                SimpleNamespace(view_channel=True) if target is role else original(target)
            )
        elif unsafe == "member":
            other = Mock(spec=discord.Member)
            other.id = OWNER + 1
            channel.overwrites[other] = discord.PermissionOverwrite(view_channel=True)
        elif unsafe == "owner":
            channel.guild.owner_id = OWNER + 1
        elif unsafe == "permissions":
            original = channel.permissions_for.side_effect
            channel.permissions_for.side_effect = lambda target: (
                SimpleNamespace(view_channel=True, send_messages=False, embed_links=True)
                if target is channel.guild.me
                else original(target)
            )
        else:
            sender.client.fetch_channel.return_value = Mock(spec=discord.Thread)
        with pytest.raises(DeliveryFailure) as failure:
            await sender.send(claim)
        assert failure.value.permanent
        channel.send.assert_not_awaited()

    asyncio.run(scenario())


def test_unapproved_explicit_channel_and_foreign_owner_claim_are_denied(authorization):
    async def scenario():
        sender, claim, channel, _ = fixture(
            authorization, target="channel", fallback="234567890123456789"
        )
        claim.reminder.channel_id = "345678901234567890"
        with pytest.raises(DeliveryFailure):
            await sender.send(claim)
        channel.send.assert_not_awaited()
        claim.reminder.owner_id = str(OWNER + 1)
        with pytest.raises(DeliveryFailure):
            await sender.send(claim)

    asyncio.run(scenario())


def test_owner_guard_precedes_channel_fetch(authorization):
    async def scenario():
        sender, _, _, _ = fixture(authorization)
        with pytest.raises(AuthorizationError):
            await sender.validate_channel(OWNER + 1, "234567890123456789")
        sender.client.fetch_channel.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure,code",
    [
        (OSError("private details"), "network_error"),
        (
            discord.HTTPException(
                SimpleNamespace(status=503, reason="Unavailable"), "private response"
            ),
            "http_error",
        ),
    ],
)
def test_transport_errors_are_classified_without_fallback_or_raw_error_storage(
    authorization, failure, code
):
    async def scenario():
        sender, claim, _, user = fixture(authorization, fallback="234567890123456789")
        user.send.side_effect = failure
        with pytest.raises(DeliveryFailure) as result:
            await sender.send(claim)
        assert result.value.code == code and not result.value.permanent
        assert "private" not in str(result.value)
        sender.client.fetch_channel.assert_not_awaited()

    asyncio.run(scenario())
