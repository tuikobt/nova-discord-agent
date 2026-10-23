"""Private Discord navigation/form state, never global screen or page state."""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import uuid4

from app.domain.modules import Screen

CORE_SCREENS = frozenset((Screen.TASKS, Screen.PROJECTS, Screen.CALENDAR, Screen.TODAY))


@dataclass(frozen=True)
class CoreRoute:
    screen: Screen
    page: int = 0
    item_id: str | None = None
    status: str | None = None
    priority: str | None = None
    project_id: str | None = None
    due_from: datetime | None = None
    due_until: datetime | None = None
    day: date | None = None
    weekly: bool = False
    parent: "CoreRoute | None" = None


@dataclass
class WriteIntent:
    route: CoreRoute
    data: object
    record: object = None
    request_id: str = field(default_factory=lambda: str(uuid4()))
    saved: object = None
    cancelled: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
