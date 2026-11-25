import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from app.domain.errors import ValidationError
from app.integrations.errors import IntegrationError
from app.integrations.github import (
    API_VERSION,
    MAX_DOCUMENT,
    MAX_RESPONSE,
    GitHubHTTP,
    GitHubReader,
    document_path,
    validate_route,
)

TOKEN = "synthetic-github-read-credential"
REPO = {"full_name": "owner/repo", "description": "Synthetic description", "default_branch": "main"}


def issue(number=1, **values):
    return dict(
        number=number, title="Synthetic item", state="open", body="Synthetic text", **values
    )


def file_data(payload=b"# Synthetic document", **values):
    return (
        dict(
            type="file",
            path="README.md",
            encoding="base64",
            size=len(payload),
            content=base64.b64encode(payload).decode(),
            sha="a" * 40,
        )
        | values
    )


class Reply:
    def __init__(self, value=REPO, *, status=200, headers=None, raw=None, length=True):
        self.payload = json.dumps(value).encode() if raw is None else raw
        self.status, self.headers = status, headers or {}
        self.content_length = len(self.payload) if length else None
        self.content = self
        self.reads = 0

    async def iter_chunked(self, size):
        self.reads += 1
        for start in range(0, len(self.payload), size):
            yield self.payload[start : start + size]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def http_fixture(reply, **kwargs):
    session = SimpleNamespace(get=Mock(return_value=reply), close=AsyncMock())
    factory = Mock(return_value=session)
    return GitHubHTTP(session_factory=factory, **kwargs), session, factory


def test_http_get_fixed_origin_headers_lifecycle_and_no_redirects():
    async def scenario():
        http, session, factory = http_fixture(Reply())
        guard = AsyncMock()
        assert await http.request("/repos/owner/repo", token=TOKEN, before_request=guard) == REPO
        args, kwargs = session.get.call_args
        assert args == ("https://api.github.com/repos/owner/repo",)
        assert kwargs["allow_redirects"] is False
        assert kwargs["headers"]["X-GitHub-Api-Version"] == API_VERSION
        assert kwargs["headers"]["Authorization"] == "Bearer " + TOKEN
        assert factory.call_args.kwargs["timeout"].total == 8
        guard.assert_awaited_once()
        await http.close()
        session.close.assert_awaited_once()
        assert http.session is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "route",
    [
        "https://evil.test/data",
        "//evil.test/data",
        "/user/repos",
        "/repos/owner/repo/actions",
        "/repos/owner/repo/../../user",
        "/repos/owner/repo?token=x",
        "/repos/owner/repo#x",
        "/repos/owner/repo/contents/%2e%2e/secret.md",
        "/repos/owner/repo/contents/.env",
        "/repos/owner/repo/issues/0",
        "/repos/owner/repo/contents/docs%2Freadme.md",
    ],
)
def test_transport_rejects_unapproved_endpoints_before_network(route):
    with pytest.raises(ValidationError):
        validate_route(route)


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/Guide.txt",
        "docs/Hướng dẫn.md",
        "LICENSE",
        "CHANGELOG",
        "docs/a b.rst",
    ],
)
def test_explicit_document_paths(path):
    assert document_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../README.md",
        "/README.md",
        "docs//README.md",
        "docs/../x.md",
        "docs\\x.md",
        "https://evil.test/README.md",
        "README.md?ref=secret",
        "README.md#x",
        "docs/%2e.md",
        ".env",
        ".github/README.md",
        "app.py",
        "image.png",
        "key.pem",
        "a/ x.md",
        "x" * 241,
    ],
)
def test_unsafe_document_paths_and_non_document_files(path):
    with pytest.raises(ValidationError):
        document_path(path)


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (401, {}, "authentication_error"),
        (403, {}, "forbidden"),
        (404, {}, "not_found"),
        (429, {}, "rate_limited"),
        (403, {"X-RateLimit-Remaining": "0"}, "rate_limited"),
        (403, {"Retry-After": "60"}, "rate_limited"),
        (301, {"Location": "https://evil.test/" + TOKEN}, "redirect_blocked"),
        (302, {}, "redirect_blocked"),
        (500, {}, "network_error"),
        (503, {}, "network_error"),
    ],
)
def test_http_status_never_reads_or_exposes_error_body(status, headers, code):
    async def scenario():
        reply = Reply(status=status, headers=headers, raw=TOKEN.encode())
        http, session, _ = http_fixture(reply)
        with pytest.raises(IntegrationError) as caught:
            await http.request("/repos/owner/repo", token=TOKEN)
        assert caught.value.code == code and TOKEN not in str(caught.value)
        assert reply.reads == 0
        if code == "rate_limited":
            with pytest.raises(IntegrationError, match="giới hạn"):
                await http.request("/repos/owner/repo", token=TOKEN)
            assert session.get.call_count == 1
        await http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "headers,raw,length,code",
    [
        ({}, b"invalid", True, "invalid_response"),
        ({"Content-Encoding": "gzip"}, b"compressed", True, "invalid_response"),
        ({}, b"x" * (MAX_RESPONSE + 1), True, "content_too_large"),
        ({}, b"x" * (MAX_RESPONSE + 1), False, "content_too_large"),
    ],
    ids=["invalid-json", "compressed", "oversized-header", "oversized-stream"],
)
def test_http_payload_bounds(headers, raw, length, code):
    async def scenario():
        http, _, _ = http_fixture(Reply(headers=headers, raw=raw, length=length))
        with pytest.raises(IntegrationError) as caught:
            await http.request("/repos/owner/repo", token=TOKEN)
        assert caught.value.code == code
        await http.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError(TOKEN), "timeout"),
        (aiohttp.ClientConnectionError(TOKEN), "network_error"),
    ],
)
def test_http_transport_error_is_safe(error, code):
    async def scenario():
        http, session, _ = http_fixture(Reply())
        session.get.side_effect = error
        with pytest.raises(IntegrationError) as caught:
            await http.request("/repos/owner/repo", token=TOKEN)
        assert caught.value.code == code and TOKEN not in str(caught.value)
        await http.close()

    asyncio.run(scenario())


def test_local_rate_budget_does_not_auto_retry():
    async def scenario():
        now = [100.0]
        http, session, _ = http_fixture(Reply(), clock=lambda: now[0])
        for _ in range(60):
            await http.request("/repos/owner/repo", token=TOKEN)
        with pytest.raises(IntegrationError, match="giới hạn"):
            await http.request("/repos/owner/repo", token=TOKEN)
        assert session.get.call_count == 60
        now[0] += 60
        await http.request("/repos/owner/repo", token=TOKEN)
        assert session.get.call_count == 61
        await http.close()

    asyncio.run(scenario())


def test_queued_request_rechecks_scope_before_opening_session():
    async def scenario():
        http, session, factory = http_fixture(Reply())
        await http.lock.acquire()
        guard = AsyncMock(side_effect=ValidationError("Scope revoked"))
        task = asyncio.create_task(
            http.request("/repos/owner/repo", token=TOKEN, before_request=guard)
        )
        await asyncio.sleep(0)
        http.lock.release()
        with pytest.raises(ValidationError):
            await task
        factory.assert_not_called()
        session.get.assert_not_called()

    asyncio.run(scenario())


def test_reader_filters_prs_from_issues_and_builds_own_links_and_pages():
    async def scenario():
        rows = [issue(number=i + 1) for i in range(10)]
        rows[0]["pull_request"] = {"url": "https://evil.test/"}
        rows[1]["html_url"] = "https://evil.test/"
        http = SimpleNamespace(request=AsyncMock(return_value=rows))
        result = await GitHubReader(http).read(
            "OWNER/REPO", "issues", token=TOKEN, page=2, state="all"
        )
        assert len(result["items"]) == 9 and result["excluded_pulls"] == 1
        assert result["may_have_more"] and result["page"] == 2
        assert result["items"][0]["source_url"] == "https://github.com/owner/repo/issues/2"
        assert "body" not in result["items"][0]
        call = http.request.await_args
        assert call.args[0] == "/repos/owner/repo/issues"
        assert call.kwargs["params"]["per_page"] == 10

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation,raw,options",
    [
        ("repository", REPO, {}),
        ("pulls", [issue()], {}),
        ("issue", issue(), dict(number=1)),
        ("pull", issue(), dict(number=1)),
        ("document", file_data(), dict(path="README.md")),
    ],
)
def test_supported_reads_have_backend_source_links(operation, raw, options):
    async def scenario():
        http = SimpleNamespace(request=AsyncMock(return_value=raw))
        result = await GitHubReader(http).read("owner/repo", operation, token=TOKEN, **options)
        assert result["source_url"].startswith("https://github.com/owner/repo")
        assert http.request.await_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "raw,code",
    [
        ([], "unsupported_file"),
        (file_data(type="dir"), "unsupported_file"),
        (file_data(type="symlink"), "unsupported_file"),
        (file_data(submodule_git_url="https://evil.test"), "unsupported_file"),
        (file_data(path="other.md"), "unsupported_file"),
        (file_data(size=MAX_DOCUMENT + 1), "content_too_large"),
        (file_data(content="%%%"), "unsupported_file"),
        (file_data(payload=b"a\x00b"), "unsupported_file"),
        (file_data(payload=b"\xff"), "unsupported_file"),
        (file_data(sha="invalid"), "invalid_response"),
    ],
)
def test_documents_reject_large_binary_invalid_or_indirect_objects(raw, code):
    async def scenario():
        reader = GitHubReader(SimpleNamespace(request=AsyncMock(return_value=raw)))
        with pytest.raises(IntegrationError) as caught:
            await reader.read("owner/repo", "document", token=TOKEN, path="README.md")
        assert caught.value.code == code

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation,options",
    [
        ("write", {}),
        ("issues", dict(page=0)),
        ("issues", dict(page=True)),
        ("issues", dict(page=101)),
        ("pulls", dict(state="unknown")),
        ("issue", dict(number=True)),
        ("pull", dict(number=-1)),
        ("document", dict(path="../x.md")),
    ],
)
def test_invalid_operation_arguments_never_call_transport(operation, options):
    async def scenario():
        http = SimpleNamespace(request=AsyncMock())
        with pytest.raises(ValidationError):
            await GitHubReader(http).read("owner/repo", operation, token=TOKEN, **options)
        http.request.assert_not_awaited()

    asyncio.run(scenario())


def test_probe_checks_four_read_surfaces_and_fences_every_resource():
    async def scenario():
        http = SimpleNamespace(request=AsyncMock(side_effect=[REPO, [], [], []]))
        guard = AsyncMock()
        result = await GitHubReader(http).check(
            token=TOKEN, resources=("owner/repo",), authorize=guard
        )
        assert result.ok and http.request.await_count == 4
        assert all(call.args == ("owner/repo",) for call in guard.await_args_list)
        for call in http.request.await_args_list:
            assert callable(call.kwargs["before_request"])

    asyncio.run(scenario())
