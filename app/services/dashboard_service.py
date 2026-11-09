from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domain.modules import MODULES, Screen
from app.domain.schemas import DashboardOverview, FeaturePage, paginate
from app.services.settings_service import SettingsService


class DashboardService:
    def __init__(self, settings: SettingsService, summary=None) -> None:
        self.settings = settings
        self.summary = summary

    async def overview(self, actor_id: int) -> DashboardOverview:
        preferences = await self.settings.get(actor_id)
        today = datetime.now(UTC).astimezone(ZoneInfo(preferences.timezone)).date()
        if self.summary is None:
            return DashboardOverview(today=today, timezone=preferences.timezone)
        tasks, done, projects, events = await self.summary.counts(
            actor_id, today, preferences.timezone
        )
        return DashboardOverview(
            today=today,
            timezone=preferences.timezone,
            tasks=tasks,
            projects=projects,
            done_tasks=done,
            events_today=events,
        )

    def features(self, screen: Screen, page: int = 0) -> FeaturePage:
        return paginate(MODULES[screen].features, page)
