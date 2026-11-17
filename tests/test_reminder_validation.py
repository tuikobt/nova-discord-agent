from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import RecurrenceType
from app.domain.errors import ValidationError
from app.domain.reminders import RecurrenceRule, ReminderData, validate_recurrence
from app.domain.time import format_local_datetime, parse_local_datetime

START = datetime(2026, 10, 25, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_reminder_contract_defaults_normalization_and_explicit_create_clock():
    data = ReminderData(title="  Nhắc học  ", next_fire_at=START)
    assert data.title == "Nhắc học"
    assert data.next_fire_at == datetime(2026, 10, 25, 13, tzinfo=UTC)
    assert data.next_fire_at.tzinfo == UTC
    assert data.validate_create(now=START - timedelta(seconds=1)) is data
    assert data.recurrence_type == "none" and data.status == "active"
    assert data.delivery_target == "dm" and data.channel_id is None
    assert data.to_storage()["recurrence_config_json"] is None
    assert format_local_datetime(data.next_fire_at).startswith("2026-10-25 20:00")
    with pytest.raises(FrozenInstanceError):
        data.title = "tampered"


@pytest.mark.parametrize("kind,weekday", [("daily", None), ("weekly", 6)])
def test_daily_and_weekly_rules_have_immutable_local_time_config(kind, weekday):
    rule = RecurrenceRule(time="20:00", weekday=weekday)
    data = ReminderData(title="Repeat", next_fire_at=START, recurrence_type=kind, recurrence=rule)
    config = data.to_storage()["recurrence_config_json"]
    assert config["timezone"] == "Asia/Ho_Chi_Minh" and config["time"] == "20:00"
    assert config.get("weekday") == weekday
    assert RecurrenceRule.from_config(config) == rule
    config["time"] = "21:00"
    assert data.to_storage()["recurrence_config_json"]["time"] == "20:00"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": " \n\t"},
        {"title": "x" * 251},
        {"title": None},
        {"next_fire_at": datetime(2026, 10, 25, 20)},
        {"next_fire_at": "2026-10-25 20:00"},
        {"status": "sent"},
        {"recurrence_type": "monthly"},
        {"recurrence_type": None},
        {"delivery_target": "public"},
        {"channel_id": "123"},
        {"delivery_target": "channel"},
        {"delivery_target": "channel", "channel_id": "0"},
        {"delivery_target": "channel", "channel_id": "１２３"},
        {"delivery_target": "channel", "channel_id": 123},
        {"delivery_target": "channel", "channel_id": str(2**64)},
        {"task_id": "other-task"},
        {"event_id": "other-event"},
        {"recurrence_type": "daily"},
        {"recurrence": RecurrenceRule(time="20:00")},
        {"recurrence_type": "weekly", "recurrence": RecurrenceRule(time="20:00")},
        {"recurrence_type": "daily", "recurrence": RecurrenceRule(time="20:00", weekday=6)},
        {"recurrence_type": "daily", "recurrence": {"time": "20:00", "timezone": "UTC"}},
        {"recurrence_type": "daily", "recurrence": RecurrenceRule(time="21:00")},
        {"recurrence_type": "weekly", "recurrence": RecurrenceRule(time="20:00", weekday=0)},
    ],
)
def test_reminder_contract_rejects_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        ReminderData(**{"title": "Test", "next_fire_at": START, **changes})


@pytest.mark.parametrize("delta", [timedelta(), timedelta(seconds=-1)])
def test_create_rejects_present_and_past_without_preventing_old_record_reads(delta):
    data = ReminderData(title="Old", next_fire_at=START + delta)
    with pytest.raises(ValidationError, match="tương lai"):
        data.validate_create(now=START)


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_create_rejects_terminal_status(status):
    with pytest.raises(ValidationError):
        ReminderData(title="Test", next_fire_at=START, status=status).validate_create(
            now=START - timedelta(minutes=1)
        )


def test_channel_input_is_only_an_id_not_a_claim_of_private_channel_authorization():
    data = ReminderData(
        title="Channel", next_fire_at=START, delivery_target="channel", channel_id="123456789"
    )
    assert data.channel_id == "123456789"
    # Permission/allowlist checks require the future service/delivery adapter (4B).


@pytest.mark.parametrize(
    "changes",
    [
        {"time": "24:00"},
        {"time": "8:00"},
        {"time": "08:60"},
        {"time": "08:00:00"},
        {"time": "０８:００"},
        {"time": None},
        {"timezone": "Mars/Nowhere"},
        {"timezone": None},
        {"weekday": True},
        {"weekday": -1},
        {"weekday": 7},
        {"weekday": 1.5},
        {"weekday": "6"},
    ],
)
def test_recurrence_rule_rejects_malformed_local_rules(changes):
    with pytest.raises(ValidationError):
        RecurrenceRule(**{"time": "20:00", **changes})


@pytest.mark.parametrize(
    "config",
    [None, [], "daily", {}, {"time": "20:00"}, {"time": "20:00", "timezone": "UTC", "sql": "x"}],
)
def test_json_config_is_strict_and_does_not_accept_unknown_fields(config):
    with pytest.raises(ValidationError):
        RecurrenceRule.from_config(config)


@pytest.mark.parametrize("weekday", range(7))
def test_all_weekdays_are_valid(weekday):
    rule = RecurrenceRule(time="20:00", weekday=weekday)
    assert validate_recurrence(RecurrenceType.WEEKLY, rule) == "weekly"


def test_recurrence_matches_wall_clock_across_dst_instead_of_a_fixed_utc_hour():
    rule = RecurrenceRule(time="09:00", timezone="America/New_York")
    before = parse_local_datetime("2026-03-07 09:00", rule.timezone)
    after = parse_local_datetime("2026-03-08 09:00", rule.timezone)
    assert rule.matches(before) and rule.matches(after)
    assert after - before == timedelta(hours=23)
    assert not rule.matches(before + timedelta(days=1))


@pytest.mark.parametrize("local", ["2026-03-08 02:30", "2026-11-01 01:30"])
def test_dst_gap_and_ambiguous_local_input_remain_rejected(local):
    with pytest.raises(ValidationError):
        parse_local_datetime(local, "America/New_York")


def test_explicit_offsets_distinguish_dst_folds_and_subminute_rules_are_rejected():
    rule = RecurrenceRule(time="01:30", timezone="America/New_York")
    first = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    second = first + timedelta(hours=1)
    assert rule.matches(first) and rule.matches(second)
    for extra in (timedelta(seconds=1), timedelta(microseconds=1)):
        with pytest.raises(ValidationError):
            ReminderData(
                title="Repeat",
                next_fire_at=START + extra,
                recurrence_type="daily",
                recurrence=RecurrenceRule(time="20:00"),
            )


def test_timezone_conversion_overflow_is_a_safe_validation_error():
    rule = RecurrenceRule(time="23:59", timezone="Pacific/Kiritimati")
    with pytest.raises(ValidationError, match="phạm vi"):
        rule.matches(datetime.max.replace(tzinfo=UTC))
