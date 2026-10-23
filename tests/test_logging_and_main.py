import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest

from app import main
from app.config import ConfigurationError
from app.logging_config import SafeJsonFormatter


@pytest.mark.parametrize("token", ["unit-test-token", 'token-with-"quote-and-\\slash'])
def test_formatter_redacts_token_and_drops_exception_text(token):
    formatter = SafeJsonFormatter((token,))
    try:
        raise RuntimeError("private exception content")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "test", logging.ERROR, "", 0, "failed %s", (token,), sys.exc_info()
        )
    record.interaction_id = 123
    rendered = formatter.format(record)
    assert token not in rendered
    assert "private exception content" not in rendered
    payload = json.loads(rendered)
    assert payload["event"] == "failed [REDACTED]"
    assert payload["error_type"] == "RuntimeError"
    assert payload["interaction_id"] == 123


def test_main_reports_configuration_failure_without_starting_bot(capsys):
    with (
        patch.object(
            main, "load_settings", side_effect=ConfigurationError("DISCORD_TOKEN bắt buộc")
        ),
        patch.object(main, "run_bot", new=AsyncMock()) as run,
    ):
        assert main.main() == 2
    run.assert_not_awaited()
    assert "DISCORD_TOKEN" in capsys.readouterr().err


def test_main_reports_safe_startup_failure(settings, capsys, caplog):
    with (
        patch.object(main, "load_settings", return_value=settings),
        patch.object(main, "configure_logging"),
        patch.object(
            main, "run_bot", new=AsyncMock(side_effect=RuntimeError(settings.discord_token))
        ),
    ):
        assert main.main() == 1
    assert settings.discord_token not in caplog.text + capsys.readouterr().err


def test_run_bot_passes_token_and_reconnect_and_cleans_up(settings):
    with (
        patch("app.main.NovaClient", autospec=True) as client_type,
        patch("app.main.Database", autospec=True) as database_type,
    ):
        client = client_type.return_value
        client.__aenter__.return_value = client
        asyncio.run(main.run_bot(settings))
    database_type.assert_called_once_with(settings.database_url)
    client.start.assert_awaited_once_with(settings.discord_token, reconnect=True)
    client.__aexit__.assert_awaited_once()
