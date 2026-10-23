import asyncio

import pytest

from app.discord_bot.checks import authorize_interaction
from app.domain.authorization import AuthorizationError


def test_only_configured_owner_is_authorized(authorization):
    assert authorization.is_owner(authorization.owner_id)
    for value in (authorization.owner_id + 1, str(authorization.owner_id), None, True):
        assert not authorization.is_owner(value)
        with pytest.raises(AuthorizationError):
            authorization.require_owner(value)


def test_owner_check_sends_nothing_for_owner(interaction, authorization):
    assert asyncio.run(authorize_interaction(interaction, authorization))
    interaction.response.send_message.assert_not_awaited()


@pytest.mark.parametrize("responded", [False, True])
def test_denial_uses_private_response_or_followup(interaction, authorization, responded):
    interaction.user.id += 1
    interaction.response.is_done.return_value = responded
    assert not asyncio.run(authorize_interaction(interaction, authorization))
    sender = interaction.followup.send if responded else interaction.response.send_message
    assert sender.await_args.kwargs["ephemeral"] is True
    assert sender.await_args.args == ("Chỉ chủ tài khoản được sử dụng NOVA.",)
