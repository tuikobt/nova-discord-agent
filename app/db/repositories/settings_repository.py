from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserSettings


class SettingsNotInitializedError(RuntimeError):
    pass


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, owner_id: str) -> tuple[User, UserSettings]:
        user = await self.session.get(User, owner_id)
        settings = await self.session.get(UserSettings, owner_id)
        if user is None or settings is None:
            raise SettingsNotInitializedError("Cài đặt chưa khởi tạo; hãy khởi động lại NOVA.")
        return user, settings
