import pytest

from app.config import (
    PROJECT_ROOT,
    ConfigurationError,
    Settings,
    database_url_from_mapping,
    load_settings,
)


def test_defaults(env_values):
    env_values.pop("TIMEZONE")
    config = Settings.from_mapping(env_values)
    assert config.timezone == "Asia/Ho_Chi_Minh"
    assert config.log_level == "INFO"
    assert config.guild_id is None
    assert config.discord_token not in repr(config)


@pytest.mark.parametrize("field", ["DISCORD_TOKEN", "DISCORD_OWNER_ID"])
def test_missing_required_configuration(env_values, field):
    env_values.pop(field)
    with pytest.raises(ConfigurationError, match=field) as error:
        Settings.from_mapping(env_values)
    assert env_values.get("DISCORD_TOKEN", "unit-test-token") not in str(error.value)


@pytest.mark.parametrize("value", ["", "replace-me", "token with spaces"])
def test_invalid_token(env_values, value):
    env_values["DISCORD_TOKEN"] = value
    with pytest.raises(ConfigurationError, match="DISCORD_TOKEN"):
        Settings.from_mapping(env_values)


@pytest.mark.parametrize("value", ["", "0", "-1", "abc", "1.2", "１２３", str(2**64)])
def test_invalid_owner_id(env_values, value):
    env_values["DISCORD_OWNER_ID"] = value
    with pytest.raises(ConfigurationError, match="DISCORD_OWNER_ID"):
        Settings.from_mapping(env_values)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-url",
        "postgresql://user:private-password@host/nova",
        "sqlite:///nova.db",
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///",
        "sqlite+aiosqlite:///file:x?uri=true",
    ],
)
def test_invalid_database_url(env_values, value):
    env_values["DATABASE_URL"] = value
    with pytest.raises(ConfigurationError, match="DATABASE_URL") as error:
        Settings.from_mapping(env_values)
    assert "private-password" not in str(error.value)


@pytest.mark.parametrize("value", ["", "Mars/Olympus", "/etc/passwd"])
def test_invalid_timezone(env_values, value):
    env_values["TIMEZONE"] = value
    with pytest.raises(ConfigurationError, match="TIMEZONE"):
        Settings.from_mapping(env_values)


def test_debug_logging_is_not_enabled(env_values):
    env_values["LOG_LEVEL"] = "DEBUG"
    with pytest.raises(ConfigurationError, match="LOG_LEVEL"):
        Settings.from_mapping(env_values)


def test_optional_development_guild(env_values):
    env_values["DISCORD_GUILD_ID"] = "234567890123456789"
    assert Settings.from_mapping(env_values).guild_id == 234567890123456789
    env_values["DISCORD_GUILD_ID"] = "invalid"
    with pytest.raises(ConfigurationError, match="DISCORD_GUILD_ID"):
        Settings.from_mapping(env_values)


def test_relative_database_path_is_anchored_to_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert database_url_from_mapping({}) == f"sqlite+aiosqlite:///{PROJECT_ROOT / 'nova.db'}"


def test_dotenv_loading_and_environment_precedence(tmp_path, monkeypatch, env_values):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=dotenv-test-token\nDISCORD_OWNER_ID=123\n", encoding="utf-8")
    for name in (*env_values, "DISCORD_GUILD_ID", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DISCORD_OWNER_ID", "456")
    result = load_settings(env_file)
    assert result.discord_token == "dotenv-test-token"
    assert result.owner_id == 456


def test_dotenv_does_not_expand_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=${NOT_A_SECRET}\nDISCORD_OWNER_ID=123\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_OWNER_ID", raising=False)
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TIMEZONE", raising=False)
    assert load_settings(env_file).discord_token == "${NOT_A_SECRET}"
