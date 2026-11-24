import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from test_agent import CONFIG

from app.agent.failures import explain_failure
from app.db.session import Database
from app.discord_bot.client import NovaClient
from app.domain.errors import ValidationError

PRIVATE = "synthetic-private-request-content"


def provider_error(kind, status, code=None):
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return kind(
        PRIVATE,
        response=httpx2.Response(status, request=request),
        body={
            "code": code,
            "message": PRIVATE,
            "prompt": PRIVATE,
        },
    )


@pytest.mark.parametrize(
    "error,code,word",
    [
        (
            APIConnectionError(
                message=PRIVATE, request=httpx2.Request("POST", "https://api.openai.com")
            ),
            "network_error",
            "kết nối",
        ),
        (APITimeoutError(httpx2.Request("POST", "https://api.openai.com")), "timeout", "quá lâu"),
        (TimeoutError(PRIVATE), "timeout", "quá lâu"),
        (provider_error(AuthenticationError, 401), "authentication_error", "khóa truy cập"),
        (provider_error(PermissionDeniedError, 403), "permission_denied", "quyền"),
        (
            provider_error(RateLimitError, 429, "insufficient_quota"),
            "insufficient_quota",
            "hạn mức",
        ),
        (provider_error(RateLimitError, 429, PRIVATE), "rate_limited", "giới hạn lượt"),
        (provider_error(BadRequestError, 400), "invalid_request", "chưa hợp lệ"),
        (provider_error(NotFoundError, 404), "invalid_request", "chưa hợp lệ"),
        (provider_error(InternalServerError, 503), "provider_error", "báo lỗi"),
        (RuntimeError(PRIVATE), "unknown_error", "chưa xử lý"),
    ],
)
def test_failures_are_actionable_without_echoing_provider_payloads(error, code, word):
    actual_code, message = explain_failure(error)
    assert actual_code == code and word in message
    assert PRIVATE not in message and "/menu" in message
    assert "kiểm tra đề xuất" in message


def test_backend_validation_stays_visible():
    assert explain_failure(ValidationError("Chọn giờ cụ thể.")) == (
        "validation_error",
        "Chọn giờ cụ thể.",
    )


def test_failed_connection_in_dm_keeps_business_data_unchanged(settings):
    async def scenario():
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        transport = SimpleNamespace(
            respond=AsyncMock(side_effect=APIConnectionError(message=PRIVATE, request=request)),
            close=AsyncMock(),
        )
        with patch("app.discord_bot.agent_controller.ResponsesClient", return_value=transport):
            db = Database(settings.database_url)
            client = NovaClient(replace(settings, ai=CONFIG), db)
            try:
                await db.initialize()
                await client.settings_service.initialize_owner(settings.owner_id, settings.timezone)
                message = SimpleNamespace(
                    id=111,
                    author=SimpleNamespace(id=settings.owner_id, bot=False),
                    guild=None,
                    content="Hôm nay có việc gì?",
                    channel=SimpleNamespace(send=AsyncMock()),
                )
                await client.on_message(message)
                rendered = message.channel.send.await_args.args[0]
                assert "kết nối" in rendered and PRIVATE not in rendered
                assert (await client.core_services.tasks.list(settings.owner_id)).total == 0
                assert await client.agent.pending.existing(settings.owner_id, "111") is None
                transport.respond.assert_awaited_once()
            finally:
                await client.close()

    asyncio.run(scenario())
