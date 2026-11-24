import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_personal import MEMORY

from app.db.session import Database
from app.discord_bot.agent_controller import AgentButton
from app.discord_bot.client import NovaClient
from app.discord_bot.views.personal import Form, MemoryView, PolicyView, ReportButton, WorkView
from app.domain.modules import Screen


def test_memory_ui_proposal_restart_private_server_approval(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await client.database.initialize()
            await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
            sent = SimpleNamespace(id=456, channel=SimpleNamespace(id=123), edit=AsyncMock())
            interaction.followup.send.return_value = sent
            await client.dashboard.personal.propose(interaction, "propose_memory", MEMORY)
            p = await client.agent.pending.existing(settings.owner_id, f"ui:{interaction.id}")
            assert p["message_id"] == "456"
            assert not (await client.core_services.personal.memories(settings.owner_id))["items"]
            assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
        finally:
            await client.close()
        restarted = NovaClient(settings, Database(settings.database_url))
        try:
            interaction.client = restarted
            interaction.guild = SimpleNamespace(id=999)
            interaction.channel_id = 123
            interaction.message.id = 456
            interaction.message.flags = SimpleNamespace(ephemeral=True)
            await AgentButton("keep", p["id"]).callback(interaction)
            assert (await restarted.core_services.personal.memories(settings.owner_id))[
                "total"
            ] == 1
            await restarted.dashboard.navigate(interaction, Screen.MEMORY, new_panel=True)
            assert isinstance(
                interaction.edit_original_response.await_args.kwargs["view"], MemoryView
            )
            assert MEMORY["content"] in str(
                interaction.edit_original_response.await_args.kwargs["embed"].to_dict()
            )
        finally:
            await restarted.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["owner", "expired_form", "expired_panel"])
def test_new_memory_forms_fail_closed(settings, interaction, case):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            view = MemoryView(client.dashboard.personal, dict(items=[], total=0, page=0), "")
            handler = AsyncMock()
            form = Form(view, "Synthetic", [("Nội dung", "Synthetic", 1000)], handler)
            if case == "owner":
                interaction.user.id += 1
            elif case == "expired_form":
                form.expires = 0
            else:
                view.expires_at = 0
            await form.on_submit(interaction)
            handler.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_report_button_survives_restart_binding_and_denies_nonowner(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await client.database.initialize()
            await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
            from test_agent import NOW
            from test_automation import current_run, enable

            env = SimpleNamespace(owner=settings.owner_id, database=client.database)
            client.core_services.personal.clock = lambda: NOW
            client.agent.pending.clock = lambda: NOW
            await enable(env, client.core_services, client.agent.pending)
            await client.core_services.automation.tick(
                SimpleNamespace(send=AsyncMock(return_value=("456", "123")))
            )
            row = await current_run(env)
            button = ReportButton(row.id)
            match = button.template.fullmatch(button.item.custom_id)
            restored = await ReportButton.from_custom_id(None, button.item, match)
            interaction.client, interaction.channel_id = client, 123
            interaction.message.id = 456
            await restored.callback(interaction)
            assert (
                "Bản tin sáng"
                in interaction.edit_original_response.await_args.kwargs["embed"].description
            )
            interaction.edit_original_response.reset_mock()
            interaction.user.id += 1
            await restored.callback(interaction)
            interaction.edit_original_response.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_work_and_policy_controls_construct_with_discord_limits(settings):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await client.database.initialize()
            await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
            data = await client.core_services.personal.settings(settings.owner_id)
            for view in [
                WorkView(client.dashboard.personal, data["work"]),
                PolicyView(client.dashboard.personal, data["policies"]["weekly"]),
            ]:
                assert len(view.children) <= 25 and view.timeout == 600
                for item in view.children:
                    assert item.row < 5
        finally:
            await client.close()

    asyncio.run(scenario())


def test_unbound_or_public_memory_approval_never_executes(settings, interaction):
    async def scenario():
        client = NovaClient(settings, Database(settings.database_url))
        try:
            await client.database.initialize()
            await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
            p = await client.agent.pending.propose(
                settings.owner_id, "propose_memory", MEMORY, turn="one"
            )
            interaction.client = client
            interaction.guild = SimpleNamespace(id=999)
            interaction.message.flags = SimpleNamespace(ephemeral=False)
            await AgentButton("keep", p["id"]).callback(interaction)
            assert not (await client.core_services.personal.memories(settings.owner_id))["items"]
        finally:
            await client.close()

    asyncio.run(scenario())
