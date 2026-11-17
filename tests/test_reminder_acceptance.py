"""Whole-client restart acceptance, with real SQLite and mocked Discord HTTP only."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.db.session import Database
from app.discord_bot.client import NovaClient
from app.discord_bot.views.reminders import NotificationButton
from app.domain.reminders import ReminderData

START = datetime(2026, 11, 15, 13, tzinfo=UTC)


def set_clock(client, clock):
    service = client.core_services.reminders
    service.clock = lambda: clock[0]
    service.approvals.clock = service.clock


def test_send_restart_restore_notification_snooze_and_deliver_from_same_database(
    settings, interaction
):
    async def scenario():
        clock = [START - timedelta(minutes=1)]
        first = NovaClient(settings, Database(settings.database_url))
        set_clock(first, clock)
        message = SimpleNamespace(id=123456789012345678, edit=AsyncMock())
        user = SimpleNamespace(send=AsyncMock(return_value=message))
        try:
            with patch.object(first.tree, "sync", new=AsyncMock(return_value=[])):
                await first.setup_hook()
            row = await first.core_services.reminders.create(
                settings.owner_id,
                ReminderData(title="Acceptance only", next_fire_at=START),
                request_id="restart-acceptance",
            )
            clock[0] = START
            with patch.object(first, "get_user", return_value=user):
                await first.reminder_dispatcher.tick()
            user.send.assert_awaited_once()
            history = await first.core_services.reminders.history(settings.owner_id, row.id)
            delivery_id = history[0].id
            original = NotificationButton("snooze", delivery_id)
            custom_id = original.item.custom_id
        finally:
            await first.close()

        # A new client, new controller/service instances, and a new database engine.
        second = NovaClient(settings, Database(settings.database_url))
        set_clock(second, clock)
        second_message = SimpleNamespace(id=234567890123456789, edit=AsyncMock())
        second_user = SimpleNamespace(send=AsyncMock(return_value=second_message))
        try:
            with patch.object(second.tree, "sync", new=AsyncMock(return_value=[])):
                await second.setup_hook()
            assert second.core_services.reminders is not first.core_services.reminders
            assert (
                await second.core_services.reminders.get(settings.owner_id, row.id)
            ).status == "done"
            match = re.fullmatch(
                r"nova:reminder:v1:(?P<action>done|snooze|cancel):(?P<delivery>[0-9a-f-]{36})",
                custom_id,
            )
            restored = await NotificationButton.from_custom_id(interaction, original.item, match)
            interaction.client, interaction.message = second, message
            interaction.response.is_done.return_value = False
            await restored.callback(interaction)
            assert len(await second.core_services.reminders.history(settings.owner_id, row.id)) == 2
            with patch.object(second, "get_user", return_value=second_user):
                await second.reminder_dispatcher.tick()
                second_user.send.assert_not_awaited()
                clock[0] += timedelta(minutes=15)
                await second.reminder_dispatcher.tick()
                await second.reminder_dispatcher.tick()
            second_user.send.assert_awaited_once()
            history = await second.core_services.reminders.history(settings.owner_id, row.id)
            assert len(history) == 2 and all(item.status == "sent" for item in history)
        finally:
            await second.close()

    asyncio.run(scenario())


def test_shutdown_during_send_keeps_recoverable_claim_and_releases_process_lock(core_factory):
    async def scenario():
        from app.domain.reminder_delivery import CLAIM_LEASE
        from app.scheduler.dispatcher import ReminderDispatcher
        from app.services.reminder_service import ReminderService

        async with core_factory() as env:
            clock = [START - timedelta(minutes=1)]
            service = ReminderService(
                env.database.sessions, env.tasks.authorization, clock=lambda: clock[0]
            )
            await service.create(
                env.owner,
                ReminderData(title="Shutdown test", next_fire_at=START),
                request_id="shutdown",
            )
            started = asyncio.Event()
            never_complete = asyncio.Event()

            async def blocked_send(claim):
                started.set()
                await never_complete.wait()
                return "123456789"

            sender = SimpleNamespace(
                send=AsyncMock(side_effect=blocked_send), available=Mock(return_value=True)
            )
            dispatcher = ReminderDispatcher(service, sender)
            clock[0] = START
            dispatcher.start()
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                await dispatcher.stop()
                assert not service.lock.locked()
                records = await service.list(env.owner)
                delivery = (await service.history(env.owner, records.items[0].id))[0]
                assert delivery.status == "claimed" and delivery.discord_message_id is None
                clock[0] += CLAIM_LEASE + timedelta(seconds=1)
                sender.send.side_effect = None
                sender.send.return_value = "123456789"
                await dispatcher.tick()
                assert (await service.history(env.owner, records.items[0].id))[0].status == "sent"
            finally:
                await dispatcher.stop()

    asyncio.run(scenario())
