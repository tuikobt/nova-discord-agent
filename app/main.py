"""Run from the project root with: python -m app.main."""

import asyncio
import logging
import sys

from app.config import ConfigurationError, Settings, load_settings
from app.db.session import Database
from app.discord_bot.client import NovaClient
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run_bot(settings: Settings) -> None:
    database = Database(settings.database_url)
    async with NovaClient(settings, database) as bot:
        await bot.start(settings.discord_token, reconnect=True)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Lỗi cấu hình: {error}", file=sys.stderr)
        return 2
    configure_logging(settings.log_level, settings.discord_token)
    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("bot_stopped")
    except Exception as error:
        logger.error("startup_failed", extra={"error_type": type(error).__name__})
        print(
            "Không thể chạy NOVA. Kiểm tra cấu hình, quyền Discord, kết nối và database; "
            "xem error_type trong log. Không chia sẻ token.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
