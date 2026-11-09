"""Short-lived manual pending actions for P3; no AI executor or P5 SQL table.

Tokens are service-issued, owner/payload/version/conflict bound, consumed only after commit.
They intentionally expire on process restart, just like the future private confirmation UI.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.errors import ApprovalInvalidError, ValidationError


@dataclass(frozen=True)
class ApprovalRequest:
    token: str = field(repr=False)
    reason: str
    expires_at: datetime
    before: object
    after: object
    conflicts: tuple


class ApprovalStore:
    def __init__(self, *, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(UTC))
        self._pending: dict[str, tuple[str, str, datetime]] = {}

    def issue(self, owner: str, fingerprint: str, *, reason: str, before, after, conflicts=()):
        now = self.clock()
        self._pending = {key: item for key, item in self._pending.items() if item[2] > now}
        if len(self._pending) >= 100:
            raise ValidationError("Có quá nhiều phiên xác nhận. Hãy đợi phiên cũ hết hạn.")
        token, expires = secrets.token_urlsafe(32), now + timedelta(minutes=5)
        self._pending[token] = owner, fingerprint, expires
        return ApprovalRequest(token, reason, expires, before, after, tuple(conflicts))

    def check(self, token: str, owner: str, fingerprint: str) -> None:
        item = self._pending.get(token) if isinstance(token, str) else None
        if item is None or item[0] != owner or item[1] != fingerprint or item[2] <= self.clock():
            raise ApprovalInvalidError()

    def consume(self, token: str | None) -> None:
        if token is not None:
            self._pending.pop(token, None)
