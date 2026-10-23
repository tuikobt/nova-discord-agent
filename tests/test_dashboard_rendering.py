import asyncio
from dataclasses import replace
from datetime import UTC, datetime, time
from unittest.mock import patch

import pytest

from app.discord_bot.renderers.dashboard import (
    ANCHOR_MARKER,
    TITLE,
    render_dashboard,
    render_help,
    render_module,
    render_settings,
)
from app.domain.modules import MODULES
from app.domain.schemas import DashboardLocation, paginate
from app.services.dashboard_service import DashboardService


def fields(embed):
    return {field.name: field.value for field in embed.fields}


def test_public_dashboard_contains_no_fake_counts_or_private_preferences():
    embed = render_dashboard()
    assert embed.title == TITLE
    assert embed.footer.text == ANCHOR_MARKER
    values = fields(embed)
    for label in ("Tasks", "Projects"):
        assert values[label] == "Xem trong bảng riêng"
    assert values["Reminders"] == "Sắp ra mắt"
    assert "Hôm nay" not in values
    assert "Sắp ra mắt" in values["Trạng thái các module"]
    assert "Memory" in values["Trạng thái các module"]
    assert "Settings: Đã có giao diện" in values["Trạng thái các module"]
    assert len(embed) < 6000


@pytest.mark.parametrize("screen", [screen for screen in MODULES if not MODULES[screen].available])
def test_unavailable_modules_only_offer_descriptions(screen):
    spec = MODULES[screen]
    embed = render_module(screen, paginate(spec.features))
    assert spec.title in embed.title
    assert fields(embed)["Trạng thái"] == "🔒 Sắp ra mắt"
    assert "Chưa có dữ liệu" in fields(embed)["Dữ liệu"]
    assert not spec.available
    assert len(embed.fields) <= 25
    assert all(len(field.value) <= 1024 for field in embed.fields)


def test_settings_are_real_preferences_and_automation_is_inactive(preferences):
    snapshot = replace(
        preferences,
        timezone="UTC",
        locale="vi-VN",
        morning_briefing_time=time(8, 15),
        dm_notifications_enabled=False,
    )
    embed = render_settings(snapshot)
    values = fields(embed)
    assert values["Timezone"] == "UTC"
    assert "vi-VN" in values["Language"]
    assert values["Morning Briefing"] == "08:15 • Chưa kích hoạt"
    assert values["Daily Review"] == "Chưa đặt giờ • Chưa kích hoạt"
    assert "Tắt" in values["Notification Preferences"]
    assert "Chưa kích hoạt" in values["Notification Preferences"]
    assert "Owner Access" in values
    assert "Đã lưu" not in embed.description
    assert "Đã lưu" in render_settings(snapshot, saved=True).description


def test_overview_uses_persisted_timezone_and_missing_metrics(settings_mock):
    service = DashboardService(settings_mock)
    with patch("app.services.dashboard_service.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 23, 18, 30, tzinfo=UTC)
        overview = asyncio.run(service.overview(settings_mock.authorization.owner_id))
    assert overview.today.isoformat() == "2026-10-24"
    assert overview.tasks is overview.projects is overview.reminders is None
    embed = render_dashboard(overview)
    assert "24/10/2026" in fields(embed)["Hôm nay"]
    assert embed.footer.text != ANCHOR_MARKER


def test_feature_pagination_is_bounded_and_handles_empty_lists():
    items = ("a", "b", "c", "d", "e")
    assert paginate(items).items == items[:4]
    assert paginate(items, 1).items == ("e",)
    assert paginate(()).total == 1
    assert paginate(()).items == ()
    for page in (-1, 2, True):
        with pytest.raises(ValueError):
            paginate(items, page)
    with pytest.raises(ValueError):
        paginate(items, size=0)


@pytest.mark.parametrize("channel,message", [(0, 1), (1, -1), (1, 2**64), (True, 2)])
def test_dashboard_ids_are_validated(channel, message):
    with pytest.raises(ValueError):
        DashboardLocation(channel, message)


def test_help_explains_private_panels_back_refresh_and_timeout():
    embed = render_help()
    rendered = str(embed.to_dict())
    for text in ("Back", "Refresh", "Sắp ra mắt", "10 phút", "Settings"):
        assert text in rendered
