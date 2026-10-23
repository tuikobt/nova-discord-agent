import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import Settings
from app.domain.authorization import OwnerAuthorization

OWNER_ID = 123456789012345678


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
    return SimpleNamespace(
        id=987654321012345678,
        user=SimpleNamespace(id=OWNER_ID),
        response=SimpleNamespace(is_done=Mock(return_value=False), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
