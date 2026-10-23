import asyncio
from unittest.mock import Mock

import pytest

from app.db.repositories.settings_repository import SettingsNotInitializedError
from app.db.session import Database
from app.domain.authorization import AuthorizationError
from app.domain.schemas import DashboardLocation
from app.services.settings_service import SettingsService


def test_settings_update_and_dashboard_location_survive_restart(settings, authorization):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            service = SettingsService(database.sessions, authorization)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            initial = await service.get(settings.owner_id)
            assert initial.locale == "vi-VN"
            assert initial.dashboard is None
            assert initial.morning_briefing_time is None
            await service.update_timezone(settings.owner_id, "UTC")
            location = DashboardLocation(234567890123456789, 345678901234567890)
            await service.save_dashboard(settings.owner_id, location)
        finally:
            await database.close()
        restarted = Database(settings.database_url)
        try:
            await restarted.initialize()
            service = SettingsService(restarted.sessions, authorization)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            snapshot = await service.get(settings.owner_id)
            assert snapshot.timezone == "UTC"
            assert snapshot.dashboard == location
            assert snapshot.dm_notifications_enabled is True
            assert snapshot.locale == initial.locale
        finally:
            await restarted.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "method,args",
    [
        ("get", ()),
        ("update_timezone", ("UTC",)),
        ("save_dashboard", (DashboardLocation(123, 456),)),
    ],
)
def test_settings_methods_deny_non_owner_before_db(authorization, method, args):
    sessions = Mock()
    service = SettingsService(sessions, authorization)
    with pytest.raises(AuthorizationError):
        asyncio.run(getattr(service, method)(authorization.owner_id + 1, *args))
    sessions.begin.assert_not_called()


def test_empty_database_has_explicit_uninitialized_state(settings, authorization):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            service = SettingsService(database.sessions, authorization)
            with pytest.raises(SettingsNotInitializedError):
                await service.get(settings.owner_id)
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("timezone", ["", "Mars/Nowhere", "/etc/passwd", "x" * 65])
def test_invalid_timezone_does_not_overwrite_preferences(settings, authorization, timezone):
    async def scenario():
        database = Database(settings.database_url)
        try:
            await database.initialize()
            service = SettingsService(database.sessions, authorization)
            await service.initialize_owner(settings.owner_id, settings.timezone)
            with pytest.raises((ValueError, KeyError)):
                await service.update_timezone(settings.owner_id, timezone)
            assert (await service.get(settings.owner_id)).timezone == settings.timezone
        finally:
            await database.close()

    asyncio.run(scenario())
