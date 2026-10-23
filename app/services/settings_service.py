from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories.user_repository import UserRepository
from app.domain.authorization import OwnerAuthorization


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
