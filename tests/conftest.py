import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import Settings
from app.db.session import Database
from app.discord_bot.dashboard_controller import DashboardController
from app.domain.authorization import OwnerAuthorization
from app.domain.core import Page, ProjectProgress
from app.domain.schemas import SettingsSnapshot
from app.services.calendar_service import CalendarService
from app.services.core_management import CoreServices, SummaryService
from app.services.project_service import ProjectService
from app.services.settings_service import SettingsService
from app.services.task_service import TaskService

OWNER_ID = 123456789012345678


@pytest.fixture
def core_factory(settings, authorization):
    @asynccontextmanager
    async def factory(*, approvals=None):
        database = Database(settings.database_url)
        try:
            await database.initialize()
            await SettingsService(database.sessions, authorization).initialize_owner(
                settings.owner_id, settings.timezone
            )
            yield SimpleNamespace(
                database=database,
                projects=ProjectService(database.sessions, authorization, approvals=approvals),
                tasks=TaskService(database.sessions, authorization, approvals=approvals),
                calendar=CalendarService(database.sessions, authorization, approvals=approvals),
                owner=settings.owner_id,
            )
        finally:
            await database.close()

    return factory


@pytest.fixture
def core_ui_factory(core_factory, discord_client):
    @asynccontextmanager
    async def factory():
        async with core_factory() as env:
            authorization = env.tasks.authorization
            preferences = SettingsService(env.database.sessions, authorization)
            bundle = CoreServices(env.database.sessions, authorization)
            controller = DashboardController(discord_client, authorization, preferences, bundle)
            yield env, controller

    return factory


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unit tests must not connect to external services")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def env_values(tmp_path):
    return {
        "DISCORD_TOKEN": "unit-test-token",
        "DISCORD_OWNER_ID": str(OWNER_ID),
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'nova.db'}",
        "TIMEZONE": "Asia/Ho_Chi_Minh",
    }


@pytest.fixture
def settings(env_values):
    return Settings.from_mapping(env_values)


@pytest.fixture
def authorization():
    return OwnerAuthorization(OWNER_ID)


@pytest.fixture
def interaction():
    response = SimpleNamespace(
        is_done=Mock(return_value=False),
        send_message=AsyncMock(),
        defer=AsyncMock(),
        send_modal=AsyncMock(),
    )

    async def deferred(**kwargs):
        response.is_done.return_value = True

    response.defer.side_effect = deferred
    return SimpleNamespace(
        id=987654321012345678,
        user=SimpleNamespace(id=OWNER_ID),
        response=response,
        followup=SimpleNamespace(send=AsyncMock()),
        guild_id=None,
        channel_id=234567890123456789,
        channel=None,
        message=SimpleNamespace(id=345678901234567890, edit=AsyncMock()),
        edit_original_response=AsyncMock(return_value=SimpleNamespace(edit=AsyncMock())),
    )


@pytest.fixture
def command_controller():
    return SimpleNamespace(menu=AsyncMock(), navigate=AsyncMock())


@pytest.fixture
def preferences():
    return SettingsSnapshot("Asia/Ho_Chi_Minh", "vi-VN", None, None, True, None)


@pytest.fixture
def settings_mock(authorization, preferences):
    service = Mock(spec=SettingsService)
    service.authorization = authorization
    service.get.return_value = preferences
    return service


@pytest.fixture
def discord_client():
    return SimpleNamespace(
        user=SimpleNamespace(id=456789012345678901),
        get_channel=Mock(),
        fetch_channel=AsyncMock(),
        add_view=Mock(),
    )


@pytest.fixture
def core_services_mock():
    services = SimpleNamespace(
        projects=Mock(spec=ProjectService),
        tasks=Mock(spec=TaskService),
        calendar=Mock(spec=CalendarService),
        summary=Mock(spec=SummaryService),
    )
    for service in (services.projects, services.tasks, services.calendar):
        service.list.return_value = Page((), 0, 0, 5)
    services.projects.progress.return_value = ProjectProgress(0, 0)
    services.calendar.list_day.return_value = Page((), 0, 0, 5)
    services.calendar.list_week.return_value = Page((), 0, 0, 5)
    services.summary.counts.return_value = (0, 0, 0, 0)
    services.summary.today_tasks.return_value = ((), 0)
    return services


@pytest.fixture
def controller(authorization, settings_mock, discord_client, core_services_mock):
    return DashboardController(discord_client, authorization, settings_mock, core_services_mock)
