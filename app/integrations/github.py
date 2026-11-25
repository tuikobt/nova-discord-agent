"""Bounded GitHub REST reads. No writes, arbitrary URLs, downloads or code execution."""

import asyncio
import base64
import binascii
import json
import re
from collections import deque
from pathlib import PurePosixPath
from time import monotonic, time
from urllib.parse import quote, unquote

import aiohttp

from app.domain.connections import resource_key
from app.domain.errors import DomainError, ValidationError
from app.integrations.errors import IntegrationError
from app.integrations.protocol import ProbeResult

API_ORIGIN = "https://api.github.com"
API_VERSION = "2026-03-10"
MAX_RESPONSE = 256 * 1024
MAX_DOCUMENT = 32 * 1024
PAGE_SIZE = 10


def document_path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 240:
        raise ValidationError("Nhập đường dẫn tài liệu trong repo, ví dụ README.md.")
    parts = value.split("/")
    if any(
        not part
        or part.startswith(".")
        or part != part.strip()
        or any(not (c.isalnum() or c in "_-. ") for c in part)
        for part in parts
    ):
        raise ValidationError("Đường dẫn tài liệu không hợp lệ; không nhập URL hoặc đường dẫn ẩn.")
    path = PurePosixPath(value)
    if path.suffix.lower() not in {".md", ".txt", ".rst", ".adoc"} and path.name.upper() not in {
        "README",
        "LICENSE",
        "CHANGELOG",
        "NOTICE",
        "COPYING",
    }:
        raise ValidationError("Chọn tài liệu .md, .txt, .rst, .adoc hoặc README/LICENSE.")
    return value


def validate_route(route):
    if not isinstance(route, str) or any(c in route for c in "?#\\\r\n"):
        raise ValidationError("Đường dẫn API không hợp lệ.")
    decoded = unquote(route)
    parts = decoded.split("/")
    if len(parts) < 4 or parts[:2] != ["", "repos"]:
        raise ValidationError("Đường dẫn API không hợp lệ.")
    repo = resource_key("github", "/".join(parts[2:4]))
    if "/repos/" + repo != "/".join(parts[:4]) or quote(decoded, safe="/") != route:
        raise ValidationError("Đường dẫn API không hợp lệ.")
    tail = parts[4:]
    if not tail or tail == ["contents"]:
        return
    if tail[0] in {"issues", "pulls"} and (
        len(tail) == 1 or len(tail) == 2 and re.fullmatch(r"[1-9][0-9]{0,8}", tail[1])
    ):
        return
    if tail[0] == "contents" and len(tail) > 1:
        document_path("/".join(tail[1:]))
        return
    raise ValidationError("Endpoint GitHub không được cấp quyền đọc.")


class GitHubHTTP:
    def __init__(self, *, session_factory=aiohttp.ClientSession, clock=monotonic, epoch=time):
        self.session_factory, self.clock, self.epoch = session_factory, clock, epoch
        self.session, self.cooldown = None, 0
        self.requests, self.lock = deque(), asyncio.Lock()

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def request(self, route, *, token, params=None, before_request=None):
        # Only GitHubReader constructs routes; reject URL/query/fragment injection here too.
        validate_route(route)
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise IntegrationError("missing_credential")
        async with self.lock:
            if before_request is not None:
                await before_request()
            now = self.clock()
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if now < self.cooldown or len(self.requests) >= 60:
                raise IntegrationError("rate_limited")
            self.requests.append(now)
            if self.session is None:
                self.session = self.session_factory(
                    timeout=aiohttp.ClientTimeout(total=8, connect=3),
                    trust_env=True,
                    auto_decompress=False,
                )
            try:
                async with self.session.get(
                    API_ORIGIN + route,
                    params=params,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/vnd.github+json",
                        "Accept-Encoding": "identity",
                        "X-GitHub-Api-Version": API_VERSION,
                    },
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        code = {
                            401: "authentication_error",
                            403: "forbidden",
                            404: "not_found",
                            429: "rate_limited",
                        }.get(response.status, "network_error")
                        if 300 <= response.status < 400:
                            code = "redirect_blocked"
                        if response.status in {403, 429} and (
                            response.status == 429
                            or response.headers.get("Retry-After")
                            or response.headers.get("X-RateLimit-Remaining") == "0"
                        ):
                            code = "rate_limited"
                            delay = 60
                            for name, offset in (
                                ("Retry-After", 0),
                                ("X-RateLimit-Reset", self.epoch()),
                            ):
                                try:
                                    delay = max(delay, int(response.headers.get(name, "")) - offset)
                                except ValueError:
                                    pass
                            self.cooldown = self.clock() + delay
                        raise IntegrationError(code)
                    if response.headers.get("Content-Encoding", "identity") != "identity":
                        raise IntegrationError("invalid_response")
                    if (
                        response.content_length is not None
                        and response.content_length > MAX_RESPONSE
                    ):
                        raise IntegrationError("content_too_large")
                    data = bytearray()
                    async for block in response.content.iter_chunked(16384):
                        data.extend(block)
                        if len(data) > MAX_RESPONSE:
                            raise IntegrationError("content_too_large")
                    try:
                        return json.loads(data.decode("utf-8"))
                    except (ValueError, UnicodeError, RecursionError):
                        raise IntegrationError("invalid_response") from None
            except TimeoutError:
                raise IntegrationError("timeout") from None
            except aiohttp.ClientError:
                raise IntegrationError("network_error") from None


def text_field(value, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise IntegrationError("invalid_response")
    return value[:limit]


class GitHubReader:
    def __init__(self, http):
        self.http = http

    async def read(
        self,
        repo,
        operation,
        *,
        token,
        page=1,
        state="open",
        number=None,
        path=None,
        authorize=None,
    ):
        repo = resource_key("github", repo)
        prefix = "/repos/" + repo
        source = "https://github.com/" + repo
        params = None
        if operation == "repository":
            route = prefix
        elif operation in {"issues", "pulls"}:
            if (
                type(page) is not int
                or not 1 <= page <= 100
                or state not in {"open", "closed", "all"}
            ):
                raise ValidationError("Trang hoặc trạng thái GitHub không hợp lệ.")
            route = prefix + "/" + operation
            params = dict(
                page=page, per_page=PAGE_SIZE, state=state, sort="updated", direction="desc"
            )
        elif operation in {"issue", "pull"}:
            if type(number) is not int or not 1 <= number <= 999999999:
                raise ValidationError("Số issue/PR không hợp lệ.")
            route = prefix + ("/issues/" if operation == "issue" else "/pulls/") + str(number)
        elif operation == "document":
            path = document_path(path)
            route = prefix + "/contents/" + quote(path, safe="/")
        else:
            raise ValidationError("Chức năng đọc GitHub không hợp lệ.")
        raw = await self.http.request(
            route,
            token=token,
            params=params,
            before_request=(lambda: authorize(repo)) if authorize else None,
        )
        if operation == "repository":
            if not isinstance(raw, dict) or str(raw.get("full_name", "")).casefold() != repo:
                raise IntegrationError("invalid_response")
            return dict(
                kind=operation,
                repository=repo,
                source_url=source,
                description=text_field(raw.get("description"), 1000),
                default_branch=text_field(raw.get("default_branch"), 250),
            )
        if operation in {"issues", "pulls"}:
            if not isinstance(raw, list) or len(raw) > PAGE_SIZE:
                raise IntegrationError("invalid_response")
            if any(not isinstance(row, dict) for row in raw):
                raise IntegrationError("invalid_response")
            items = [
                self.item(repo, row, operation == "pulls")
                for row in raw
                if operation == "pulls" or "pull_request" not in row
            ]
            return dict(
                kind=operation,
                repository=repo,
                source_url=source + "/" + operation,
                items=items,
                page=page,
                state=state,
                may_have_more=len(raw) == PAGE_SIZE and page < 100,
                excluded_pulls=len(raw) - len(items),
            )
        if operation in {"issue", "pull"}:
            if not isinstance(raw, dict) or raw.get("number") != number:
                raise IntegrationError("invalid_response")
            if operation == "issue" and "pull_request" in raw:
                raise ValidationError("Đây là pull request; hãy mở danh sách PR để đọc.")
            return dict(
                kind=operation,
                repository=repo,
                **self.item(repo, raw, operation == "pull", include_body=True),
            )
        if (
            not isinstance(raw, dict)
            or raw.get("type") != "file"
            or raw.get("submodule_git_url")
            or raw.get("path") != path
            or raw.get("encoding") != "base64"
        ):
            raise IntegrationError("unsupported_file")
        size = raw.get("size")
        if type(size) is not int or size < 0 or size > MAX_DOCUMENT:
            raise IntegrationError("content_too_large")
        try:
            encoded = raw["content"]
            if not isinstance(encoded, str):
                raise ValueError
            decoded = base64.b64decode("".join(encoded.split()), validate=True)
            if len(decoded) != size or len(decoded) > MAX_DOCUMENT:
                raise ValueError
            content = decoded.decode("utf-8")
            if any(ord(c) < 32 and c not in "\n\r\t" for c in content):
                raise ValueError
        except (KeyError, ValueError, binascii.Error, UnicodeError):
            raise IntegrationError("unsupported_file") from None
        sha = raw.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise IntegrationError("invalid_response")
        return dict(
            kind=operation,
            repository=repo,
            path=path,
            body=content,
            sha=sha,
            source_url=source + "/blob/HEAD/" + quote(path, safe="/"),
            truncated=False,
        )

    def item(self, repo, row, pull, *, include_body=False):
        number = row.get("number")
        if type(number) is not int or number < 1 or row.get("state") not in {"open", "closed"}:
            raise IntegrationError("invalid_response")
        result = dict(
            number=number,
            title=text_field(row.get("title"), 250),
            state=row["state"],
            source_url=f"https://github.com/{repo}/{'pull' if pull else 'issues'}/{number}",
        )
        if include_body:
            body = row.get("body") or ""
            result.update(body=text_field(body, 6000), truncated=len(body) > 6000)
        return result

    async def check(self, *, token, resources, authorize):
        try:
            for repo in resources:
                for operation in ("repository", "issues", "pulls", "contents"):
                    await authorize(repo)
                    if operation == "contents":
                        raw = await self.http.request(
                            "/repos/" + repo + "/contents",
                            token=token,
                            before_request=lambda resource=repo: authorize(resource),
                        )
                        if not isinstance(raw, list):
                            raise IntegrationError("invalid_response")
                    else:
                        await self.read(repo, operation, token=token, authorize=authorize)
            return ProbeResult(True)
        except IntegrationError as error:
            return ProbeResult(False, error.code)
        except DomainError:
            raise
