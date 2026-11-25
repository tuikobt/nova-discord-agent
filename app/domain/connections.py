"""Normalize approved identifiers, never arbitrary fetch URLs or credentials."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from app.domain.core import text_value
from app.domain.errors import ValidationError

PROVIDERS = {"github": "GitHub", "notion": "Notion"}
CONNECTION_WRITES = frozenset({"configure_connection", "disconnect_connection"})


def resource_key(provider, value):
    if provider not in PROVIDERS or not isinstance(value, str) or len(value) > 400:
        raise ValidationError("Nguồn kết nối hoặc tài nguyên không hợp lệ.")
    value = value.strip()
    is_url = "://" in value
    if is_url:
        try:
            url = urlsplit(value)
            hosts = {
                "github": {"github.com", "www.github.com"},
                "notion": {"notion.so", "www.notion.so"},
            }
            if (
                url.scheme != "https"
                or url.hostname not in hosts[provider]
                or url.username
                or url.password
                or url.port not in {None, 443}
            ):
                raise ValueError
            value = url.path.strip("/")
        except ValueError:
            raise ValidationError(
                "Chỉ nhận link HTTPS chính thức của GitHub hoặc Notion."
            ) from None
    if provider == "github":
        if value.endswith(".git"):
            value = value[:-4]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}", value):
            raise ValidationError("Repo phải là tên-chủ/repo hoặc link repo GitHub.")
        if value.rsplit("/", 1)[1] in {".", ".."}:
            raise ValidationError("Tên repo không hợp lệ.")
        return value.casefold()
    match = re.search(
        r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$", value
    )
    if not match:
        raise ValidationError("Nhập ID hoặc link trang Notion có ID trang hợp lệ.")
    # A raw ID cannot have a prefix; a slug prefix is allowed only for a parsed official URL.
    if not is_url and match.start() != 0:
        raise ValidationError("ID trang Notion không hợp lệ.")
    return str(UUID(match[1]))


@dataclass(frozen=True)
class ConnectionData:
    provider: str
    label: str
    resources: list[str]

    def normalized(self, secrets):
        if self.provider not in PROVIDERS:
            raise ValidationError("Chỉ hỗ trợ cấu hình GitHub hoặc Notion.")
        label = text_value(self.label, 80)
        if not isinstance(self.resources, list) or not 1 <= len(self.resources) <= 10:
            raise ValidationError("Chọn từ 1 đến 10 repo hoặc trang.")
        if secrets.contains(label) or any(secrets.contains(v) for v in self.resources):
            raise ValidationError("Không nhập token/key trong tên hoặc phạm vi kết nối.")
        values = sorted({resource_key(self.provider, value) for value in self.resources})
        if len(values) != len(self.resources):
            raise ValidationError("Phạm vi có tài nguyên trùng nhau.")
        return dict(provider=self.provider, label=label, resources=values)
