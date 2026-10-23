from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utc_now
from app.db.repositories.settings_repository import SettingsRepository
from app.db.repositories.user_repository import UserRepository
from app.domain.authorization import OwnerAuthorization
from app.domain.schemas import DashboardLocation, SettingsSnapshot


class SettingsService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        authorization: OwnerAuthorization,
    ) -> None:
        self.sessions = sessions
        self.authorization = authorization

    async def initialize_owner(self, actor_id: int, timezone: str) -> None:
        self.authorization.require_owner(actor_id)
        ZoneInfo(timezone)
        async with self.sessions.begin() as session:
            await UserRepository(session).ensure_owner(str(actor_id), timezone)

    async def get(self, actor_id: int) -> SettingsSnapshot:
        self.authorization.require_owner(actor_id)
        async with self.sessions.begin() as session:
            user, settings = await SettingsRepository(session).get(str(actor_id))
            location = None
            if (
                settings.dashboard_channel_id is not None
                or settings.dashboard_message_id is not None
            ):
                if not settings.dashboard_channel_id or not settings.dashboard_message_id:
                    raise ValueError("Dashboard location chưa đầy đủ.")
                location = DashboardLocation(
                    int(settings.dashboard_channel_id), int(settings.dashboard_message_id)
                )
            return SettingsSnapshot(
                timezone=user.timezone,
                locale=user.locale,
                morning_briefing_time=settings.morning_briefing_time,
                daily_review_time=settings.daily_review_time,
                dm_notifications_enabled=settings.dm_notifications_enabled,
                dashboard=location,
            )

    async def update_timezone(self, actor_id: int, timezone: str) -> None:
        self.authorization.require_owner(actor_id)
        if not timezone or len(timezone) > 64:
            raise ValueError("Timezone không hợp lệ.")
        ZoneInfo(timezone)
        async with self.sessions.begin() as session:
            user, settings = await SettingsRepository(session).get(str(actor_id))
            user.timezone = timezone
            settings.updated_at = utc_now()

    async def save_dashboard(self, actor_id: int, location: DashboardLocation) -> None:
        self.authorization.require_owner(actor_id)
        if not isinstance(location, DashboardLocation):
            raise ValueError("Dashboard location không hợp lệ.")
        async with self.sessions.begin() as session:
            _, settings = await SettingsRepository(session).get(str(actor_id))
            settings.dashboard_channel_id = str(location.channel_id)
            settings.dashboard_message_id = str(location.message_id)
