import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from test_agent import CONFIG, NOW, bind, bundle, response

from app.agent.orchestrator import AgentOrchestrator
from app.config import Settings
from app.db.models import AuditLog, IntegrationConnection, PendingAction
from app.domain.authorization import AuthorizationError
from app.domain.connections import ConnectionData, resource_key
from app.domain.errors import ApprovalInvalidError, StaleWriteError, StorageError, ValidationError
from app.integrations.config import ConnectionCredentials
from app.integrations.protocol import ProbeResult
from app.security import SecretFilter
from app.services.connection_service import ConnectionService

ARGS = dict(
    connection_id=None,
    expected_version=0,
    provider="github",
    label="My work",
    resources=["Owner/Repo"],
)
SECRET = "synthetic-connection-private-credential"


def connection_bundle(env, *, credentials=None):
    core, pending, gateway, usage = bundle(env)
    core.connections = ConnectionService(
        env.database.sessions, env.tasks.authorization, credentials=credentials, clock=lambda: NOW
    )
    return core, pending, gateway, usage


async def configure(env, pending, args=None):
    p = await pending.propose(env.owner, "configure_connection", args or ARGS, turn=str(uuid4()))
    await bind(pending, env.owner, p)
    receipt = await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
    return receipt["ids"][0]


@pytest.mark.parametrize(
    "provider,value,expected",
    [
        ("github", "Owner/Repo", "owner/repo"),
        ("github", "https://github.com/Owner/Repo.git", "owner/repo"),
        ("notion", "12345678123412341234123456789abc", "12345678-1234-1234-1234-123456789abc"),
        (
            "notion",
            "https://www.notion.so/Work-12345678123412341234123456789abc?pvs=4",
            "12345678-1234-1234-1234-123456789abc",
        ),
    ],
)
def test_resources_normalize_to_identifiers_not_fetch_urls(provider, value, expected):
    assert resource_key(provider, value) == expected


@pytest.mark.parametrize(
    "provider,value",
    [
        ("github", "https://github.com.evil.test/Owner/Repo"),
        ("github", "https://secret@github.com/Owner/Repo"),
        ("github", "http://github.com/Owner/Repo"),
        ("github", "https://localhost/Owner/Repo"),
        ("github", "https://github.com:9000/Owner/Repo"),
        ("github", "Owner/Repo/issues"),
        ("github", "Owner/.."),
        ("notion", "arbitrary-prefix12345678123412341234123456789abc"),
        ("notion", "https://example.test/12345678123412341234123456789abc"),
        ("notion", "https://www.notion.so/missing-id"),
        ("unknown", "Owner/Repo"),
    ],
)
def test_unapproved_url_shapes_are_rejected(provider, value):
    with pytest.raises(ValidationError):
        resource_key(provider, value)


@pytest.mark.parametrize(
    "resources", [[], ["Owner/Repo", "owner/repo"], ["owner/repo"] * 11, [None]]
)
def test_scope_size_duplicates_and_types(resources):
    with pytest.raises(ValidationError):
        ConnectionData("github", "Work", resources).normalized(SecretFilter())


def test_credentials_are_fixed_refs_hidden_and_not_stored_in_scope(env_values):
    values = {**env_values, "GITHUB_READ_TOKEN": SECRET, "NOTION_READ_TOKEN": SECRET + "-notion"}
    settings = Settings.from_mapping(values)
    assert SECRET not in repr(settings) and SECRET not in repr(settings.connections)
    assert settings.connections.resolve("github") == SECRET
    with pytest.raises(ValueError):
        settings.connections.resolve("DISCORD_TOKEN")
    with pytest.raises(ValidationError):
        ConnectionData("github", SECRET, ["owner/repo"]).normalized(
            SecretFilter(settings.connections.registered())
        )


def test_connection_create_requires_confirmation_and_is_idempotent(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(env)
            p = await pending.propose(env.owner, "configure_connection", ARGS, turn="create")
            assert (await core.connections.list(env.owner))["total"] == 0
            with pytest.raises(ApprovalInvalidError):
                await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            await bind(pending, env.owner, p)
            receipt = await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            assert receipt == await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            data = (await core.connections.list(env.owner))["items"][0]
            assert data["status"] == "configured" and data["verified_permissions"] is None
            assert data["resources"] == ["owner/repo"]
            assert "credential" not in str(data)
            async with env.database.sessions() as session:
                row = await session.get(IntegrationConnection, receipt["ids"][0])
                assert row.credential_ref == "GITHUB_READ_TOKEN"
                assert row.created_at.tzinfo and row.updated_at == NOW
                assert len(list(await session.scalars(select(AuditLog)))) == 1

    asyncio.run(scenario())


def test_scope_gate_denies_owner_resource_write_stale_and_disconnect(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, _ = connection_bundle(env)
            key = await configure(env, pending)
            allowed = await core.connections.authorize_resource(
                env.owner, key, "OWNER/REPO", expected_version=1
            )
            assert allowed["resource"] == "owner/repo" and "token" not in allowed
            for kwargs in (
                dict(resource="other/repo", expected_version=1),
                dict(resource="owner/repo", expected_version=1, permission="write"),
            ):
                with pytest.raises(ValidationError):
                    await core.connections.authorize_resource(env.owner, key, **kwargs)
            with pytest.raises(StaleWriteError):
                await core.connections.authorize_resource(
                    env.owner, key, "owner/repo", expected_version=0
                )
            with pytest.raises(AuthorizationError):
                await core.connections.authorize_resource(
                    env.owner + 1, key, "owner/repo", expected_version=1
                )
            with pytest.raises(AuthorizationError):
                await core.connections.check(env.owner + 1, key)
            with pytest.raises(ValidationError):
                await gateway.call(
                    env.owner,
                    "configure_connection",
                    ARGS,
                    turn="ai",
                    allowed={"configure_connection"},
                )
            p = await pending.propose(
                env.owner,
                "disconnect_connection",
                dict(connection_id=key, expected_version=1),
                turn="disconnect",
            )
            await bind(pending, env.owner, p)
            await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            with pytest.raises(ValidationError):
                await core.connections.authorize_resource(
                    env.owner, key, "owner/repo", expected_version=2
                )
            assert (await core.connections.get(env.owner, key))["status"] == "disconnected"

    asyncio.run(scenario())


def test_scope_edit_invalidates_old_approval_and_clears_context(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(env)
            changed = []
            core.connections.on_change = changed.append
            key = await configure(env, pending)
            changes = {
                **ARGS,
                "connection_id": key,
                "expected_version": 1,
                "resources": ["owner/new"],
            }
            old = await pending.propose(env.owner, "configure_connection", changes, turn="old")
            await bind(pending, env.owner, old)
            await configure(env, pending, changes)
            with pytest.raises(StaleWriteError):
                await pending.decide(env.owner, old["id"], "123", "456", choice="keep")
            data = await core.connections.get(env.owner, key)
            assert data["resources"] == ["owner/new"] and data["version"] == 2
            assert changed == [env.owner, env.owner]
            with pytest.raises(ValidationError):
                await core.connections.authorize_resource(
                    env.owner, key, "owner/repo", expected_version=2
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("prefix", ["ntn_", "secret_"])
def test_unconfigured_notion_tokens_are_rejected_before_storage(prefix):
    token = prefix + "a" * 40
    with pytest.raises(ValidationError):
        ConnectionData("github", token, ["owner/repo"]).normalized(SecretFilter())


@pytest.mark.parametrize("value", [None, "replace-me", "not a valid token"])
def test_invalid_optional_credentials_do_not_break_other_features(value):
    assert not ConnectionCredentials.from_mapping({"GITHUB_READ_TOKEN": value}).resolve("github")


@pytest.mark.parametrize(
    "has_key,status", [(False, "missing_credential"), (True, "adapter_pending")]
)
def test_no_false_verified_status_without_credentials_or_provider_adapter(
    core_factory, has_key, status
):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(
                env, credentials=ConnectionCredentials(github=SECRET if has_key else "")
            )
            key = await configure(env, pending)
            result = await core.connections.check(env.owner, key)
            assert result == dict(status=status, network_attempted=False)
            record = await core.connections.get(env.owner, key)
            assert record["status"] == "configured" and record["last_checked_at"] is None

    asyncio.run(scenario())


def test_probe_never_holds_writer_and_revoke_during_probe_is_fenced(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(
                env, credentials=ConnectionCredentials(github=SECRET)
            )
            key = await configure(env, pending)

            async def probe(**kwargs):
                # A concurrent writer must be able to disconnect before HTTP returns.
                p = await pending.propose(
                    env.owner,
                    "disconnect_connection",
                    dict(connection_id=key, expected_version=1),
                    turn="revoke",
                )
                await bind(pending, env.owner, p)
                await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
                return ProbeResult(True)

            core.connections.probes["github"] = SimpleNamespace(check=AsyncMock(side_effect=probe))
            with pytest.raises(StaleWriteError):
                await core.connections.check(env.owner, key)
            assert (await core.connections.get(env.owner, key))["status"] == "disconnected"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "result,status",
    [
        (ProbeResult(True), "verified"),
        (ProbeResult(False, "forbidden"), "forbidden"),
        (ProbeResult(False, SECRET), "unknown_error"),
        ({"ok": True}, "unknown_error"),
    ],
)
def test_probe_safe_typed_results_and_versions(core_factory, result, status):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(
                env, credentials=ConnectionCredentials(github=SECRET)
            )
            key = await configure(env, pending)
            core.connections.probes["github"] = SimpleNamespace(
                check=AsyncMock(return_value=result)
            )
            checked = await core.connections.check(env.owner, key)
            assert checked["status"] == status and SECRET not in str(checked)
            row = await core.connections.get(env.owner, key)
            assert row["version"] == 2 and row["last_checked_at"] == NOW.isoformat()
            assert (row["verified_permissions"] == ["read"]) == (status == "verified")

    asyncio.run(scenario())


def test_model_cannot_receive_connection_mutation_tools(core_factory):
    async def scenario():
        async with core_factory() as env:
            core, pending, gateway, usage = connection_bundle(env)
            transport = SimpleNamespace(
                respond=AsyncMock(return_value=response(text="Bạn muốn xem kết nối nào?"))
            )
            agent = AgentOrchestrator(
                CONFIG,
                env.tasks.authorization,
                gateway,
                pending,
                usage,
                transport,
                clock=lambda: NOW,
            )
            await agent.turn(env.owner, "one", "Cập nhật quyền kết nối GitHub")
            names = {item["name"] for item in transport.respond.await_args.kwargs["tools"]}
            assert "configure_connection" not in names and "disconnect_connection" not in names
            agent.close()

    asyncio.run(scenario())


def test_connection_receipt_and_audit_roll_back_with_failed_commit(core_factory, monkeypatch):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(env)
            p = await pending.propose(env.owner, "configure_connection", ARGS, turn="atomic")
            await bind(pending, env.owner, p)
            flush = AsyncSession.flush

            async def fail(session, *args, **kwargs):
                result = await flush(session, *args, **kwargs)
                if any(
                    isinstance(row, IntegrationConnection) for row in session.identity_map.values()
                ):
                    raise SQLAlchemyError("synthetic commit failure")
                return result

            with monkeypatch.context() as patcher:
                patcher.setattr(AsyncSession, "flush", fail)
                with pytest.raises(StorageError):
                    await pending.decide(env.owner, p["id"], "123", "456", choice="keep")
            assert (await core.connections.list(env.owner))["total"] == 0
            async with env.database.sessions() as session:
                row = await session.get(PendingAction, p["id"])
                assert row.status == "pending" and row.result_json is None
                assert not list(await session.scalars(select(AuditLog)))

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error,code", [(TimeoutError(SECRET), "timeout"), (RuntimeError(SECRET), "unknown_error")]
)
def test_provider_failures_never_store_or_return_error_bodies(core_factory, error, code):
    async def scenario():
        async with core_factory() as env:
            core, pending, _, _ = connection_bundle(
                env, credentials=ConnectionCredentials(github=SECRET)
            )
            key = await configure(env, pending)
            core.connections.probes["github"] = SimpleNamespace(check=AsyncMock(side_effect=error))
            result = await core.connections.check(env.owner, key)
            assert result == dict(status=code, network_attempted=True)
            assert SECRET not in str(await core.connections.get(env.owner, key))
            async with env.database.sessions() as session:
                logs = list(await session.scalars(select(AuditLog)))
                assert SECRET not in str([log.safe_metadata_json for log in logs])

    asyncio.run(scenario())
