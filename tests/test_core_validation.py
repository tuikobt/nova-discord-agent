import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.domain.authorization import AuthorizationError
from app.domain.core import EventData, ProjectData, TaskData
from app.domain.errors import ValidationError
from app.domain.time import as_utc, format_local_datetime, parse_local_datetime
from app.services.calendar_service import CalendarService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService

START = datetime(2026, 10, 25, 13, tzinfo=UTC)
KEY = str(uuid4())
EVENT = EventData(title="E", starts_at=START, ends_at=START + timedelta(hours=1))


@pytest.mark.parametrize(
    "service_type,method,args,kwargs",
    [
        (ProjectService, "get", (KEY,), {}),
        (ProjectService, "list", (), {}),
        (ProjectService, "progress", (KEY,), {}),
        (ProjectService, "create", (ProjectData(name="P"),), {"request_id": "p"}),
        (ProjectService, "update", (KEY, ProjectData(name="P")), {"expected": START}),
        (ProjectService, "archive", (KEY,), {"expected": START}),
        (TaskService, "get", (KEY,), {}),
        (TaskService, "list", (), {}),
        (TaskService, "create", (TaskData(title="T"),), {"request_id": "t"}),
        (TaskService, "update", (KEY, TaskData(title="T")), {"expected": 1}),
        (TaskService, "set_status", (KEY, "done"), {"expected": 1}),
        (CalendarService, "get", (KEY,), {}),
        (CalendarService, "create", (EVENT,), {"request_id": "e"}),
        (CalendarService, "update", (KEY, EVENT), {"expected": 1}),
        (CalendarService, "cancel", (KEY,), {"expected": 1}),
        (CalendarService, "list", (START, START + timedelta(hours=1)), {}),
        (CalendarService, "list_day", (date(2026, 10, 25),), {}),
        (CalendarService, "list_week", (date(2026, 10, 25),), {}),
    ],
)
def test_every_service_entry_denies_non_owner_before_database(
    authorization, service_type, method, args, kwargs
):
    sessions = Mock()
    service = service_type(sessions, authorization)
    with pytest.raises(AuthorizationError):
        asyncio.run(getattr(service, method)(authorization.owner_id + 1, *args, **kwargs))
    sessions.begin.assert_not_called()


@pytest.mark.parametrize(
    "factory,values",
    [
        (ProjectData, {"name": " "}),
        (ProjectData, {"name": "x" * 201}),
        (ProjectData, {"name": "P", "status": "invalid"}),
        (ProjectData, {"name": "P", "deadline_at": START.replace(tzinfo=None)}),
        (TaskData, {"title": ""}),
        (TaskData, {"title": "x" * 251}),
        (TaskData, {"title": "T", "description": "x" * 4001}),
        (TaskData, {"title": "T", "priority": "urgent"}),
        (TaskData, {"title": "T", "status": "invalid"}),
        (TaskData, {"title": "T", "estimated_minutes": 0}),
        (TaskData, {"title": "T", "estimated_minutes": -1}),
        (TaskData, {"title": "T", "estimated_minutes": 1.5}),
        (TaskData, {"title": "T", "estimated_minutes": True}),
        (TaskData, {"title": "T", "project_id": "invalid"}),
        (TaskData, {"title": "T", "due_at": START.replace(tzinfo=None)}),
        (EventData, {"title": "E", "starts_at": START, "ends_at": START}),
        (EventData, {"title": "E", "starts_at": START, "ends_at": START - timedelta(seconds=1)}),
        (
            EventData,
            {
                "title": "E",
                "starts_at": START.replace(tzinfo=None),
                "ends_at": START + timedelta(hours=1),
            },
        ),
        (
            EventData,
            {
                "title": "E",
                "starts_at": START,
                "ends_at": START + timedelta(hours=1),
                "is_fixed": 1,
            },
        ),
        (
            EventData,
            {
                "title": "E",
                "starts_at": START,
                "ends_at": START + timedelta(hours=1),
                "task_id": "invalid",
            },
        ),
    ],
)
def test_invalid_inputs_have_consistent_validation_error(factory, values):
    with pytest.raises(ValidationError):
        factory(**values)


@pytest.mark.parametrize(
    "value",
    [
        "10/11",
        "2026-10-25",
        "2026-02-30 10:00",
        "2026-10-25 25:00",
        "2026-1-2 10:00",
        "tomorrow",
        "",
        None,
    ],
)
def test_ambiguous_or_invalid_local_dates_are_not_guessed(value):
    with pytest.raises(ValidationError):
        parse_local_datetime(value)


def test_local_datetime_conversion_rejects_dst_gaps_and_ambiguity():
    assert parse_local_datetime("2026-10-25 20:00") == START
    assert format_local_datetime(START) == "2026-10-25 20:00 (Asia/Ho_Chi_Minh)"
    for value in ("2026-03-08 02:30", "2026-11-01 01:30"):
        with pytest.raises(ValidationError):
            parse_local_datetime(value, "America/New_York")
    with pytest.raises(ValidationError):
        parse_local_datetime("2026-10-25 20:00", "Mars/Nowhere")
    with pytest.raises(ValidationError):
        as_utc(START.replace(tzinfo=None))


def test_datetime_range_boundaries_are_safe_validation_errors():
    with pytest.raises(ValidationError):
        parse_local_datetime("0001-01-01 00:00")
    with pytest.raises(ValidationError):
        format_local_datetime(datetime.max.replace(tzinfo=UTC))


@pytest.mark.parametrize(
    "method,day",
    [("list_day", date.max), ("list_week", date.max), ("list_day", "10/11"), ("list_week", START)],
)
def test_calendar_day_week_reject_invalid_or_overflowing_dates(core_factory, method, day):
    async def scenario():
        async with core_factory() as env:
            with pytest.raises(ValidationError):
                await getattr(env.calendar, method)(env.owner, day)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "service_type,data",
    [
        (ProjectService, {"name": "P"}),
        (TaskService, {"title": "T"}),
        (CalendarService, {"title": "E"}),
    ],
)
def test_services_reject_unvalidated_mappings_before_database(authorization, service_type, data):
    sessions = Mock()
    with pytest.raises(ValidationError):
        asyncio.run(
            service_type(sessions, authorization).create(
                authorization.owner_id, data, request_id="test"
            )
        )
    sessions.begin.assert_not_called()


@pytest.mark.parametrize("request_id", ["", " ", None, "x" * 129])
def test_creation_request_key_is_required_and_bounded(authorization, request_id):
    sessions = Mock()
    with pytest.raises(ValidationError):
        asyncio.run(
            TaskService(sessions, authorization).create(
                authorization.owner_id, TaskData(title="T"), request_id=request_id
            )
        )
    sessions.begin.assert_not_called()
