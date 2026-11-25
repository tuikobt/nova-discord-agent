"""Probe returns only fixed metadata, never provider content or raw errors."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    error_code: str | None = None


class ConnectionProbe(Protocol):
    async def check(
        self,
        *,
        token: str,
        resources: tuple[str, ...],
        authorize: Callable[[str], Awaitable[object]],
    ) -> ProbeResult: ...
