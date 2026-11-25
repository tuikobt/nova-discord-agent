import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from test_agent import CONFIG, response
from test_connections import ARGS, SECRET

from app.db.session import Database
from app.discord_bot.agent_controller import AgentButton
from app.discord_bot.client import NovaClient
from app.discord_bot.connections_controller import ConnectionForm, ConnectionView
from app.integrations.config import ConnectionCredentials


async def initialize(client, settings):
    await client.database.initialize()
    await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)


def test_connection_proposal_binding_and_server_restart_confirmation(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await initialize(client, settings)
            sent = SimpleNamespace(id=456, channel=SimpleNamespace(id=123), edit=AsyncMock())
            interaction.followup.send.return_value = sent
            await client.dashboard.connections.propose(interaction, "configure_connection", ARGS)
            p = await client.agent.pending.existing(
                settings.owner_id, f"connection:{interaction.id}"
            )
            assert (await client.core_services.connections.list(settings.owner_id))["total"] == 0
            assert (
                p["message_id"] == "456"
                and interaction.followup.send.await_args.kwargs["ephemeral"]
            )
        finally:
            await client.close()
        restarted = NovaClient(settings, Database(settings.database_url))
        try:
            interaction.client, interaction.channel_id = restarted, 123
            interaction.guild = SimpleNamespace(id=1)
            interaction.message.id = 456
            interaction.message.flags = SimpleNamespace(ephemeral=True)
            await AgentButton("keep", p["id"]).callback(interaction)
            items = (await restarted.core_services.connections.list(settings.owner_id))["items"]
            assert len(items) == 1 and items[0]["status"] == "configured"
            assert items[0]["verified_permissions"] is None
        finally:
            await restarted.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["owner", "form_expired", "parent_expired", "parent_closed"])
def test_connection_modal_fails_closed(settings, interaction, case):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            controller = client.dashboard.connections
            controller.propose = AsyncMock()
            parent = ConnectionView(controller)
            form = ConnectionForm(parent, "github")
            form.label_input._value, form.resources._value = "Work", "owner/repo"
            if case == "owner":
                interaction.user.id += 1
            elif case == "form_expired":
                form.expires = 0
            elif case == "parent_expired":
                parent.expires_at = 0
            else:
                parent.stop()
            await form.on_submit(interaction)
            controller.propose.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_private_diagnostics_do_not_claim_api_ready_from_configuration(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await initialize(client, settings)
            await client.dashboard.connections.open(interaction)
            embed = interaction.edit_original_response.await_args.kwargs["embed"]
            rendered = str(embed.to_dict())
            assert "Đã có bộ đọc GitHub" in rendered and "chưa có bộ đọc Notion" in rendered
            assert "Chưa bật hoặc chưa cấu hình" in rendered
            view = interaction.edit_original_response.await_args.kwargs["view"]
            assert all(item.row < 5 for item in view.children) and len(view.children) <= 25
            assert not any(isinstance(item, ConnectionForm) for item in view.children)
        finally:
            await client.close()

    asyncio.run(scenario())


def test_ai_probe_is_explicit_quota_accounted_and_does_not_echo_output(settings, interaction):
    async def scenario():
        transport = SimpleNamespace(
            respond=AsyncMock(return_value=response(text=SECRET)), close=AsyncMock()
        )
        with patch("app.discord_bot.agent_controller.ResponsesClient", return_value=transport):
            settings_with_ai = replace(
                settings, ai=CONFIG, connections=ConnectionCredentials(github=SECRET)
            )
            client = NovaClient(settings_with_ai, Database(settings.database_url))
            try:
                await initialize(client, settings)
                await client.dashboard.connections.open(interaction)
                transport.respond.assert_not_awaited()
                await client.dashboard.connections.check_ai(interaction)
                sent = interaction.followup.send.await_args.kwargs
                assert sent["ephemeral"]
                text = interaction.followup.send.await_args.args[0]
                assert SECRET not in text and "thành công" in text
                assert transport.respond.await_args.kwargs["tools"] == []
                usage = await client.agent.usage.summary(settings.owner_id)
                assert usage[0]["requests"] == 1 and usage[0]["charged_tokens"] == 120
                assert SECRET not in str(transport.respond.await_args.kwargs)
            finally:
                await client.close()

    asyncio.run(scenario())


def test_nonowner_cannot_run_ai_diagnostic(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            client.agent.usage.reserve = AsyncMock()
            interaction.user.id += 1
            await client.dashboard.connections.check_ai(interaction)
            client.agent.usage.reserve.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())
