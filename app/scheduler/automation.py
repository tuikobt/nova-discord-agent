import asyncio
import logging

logger = logging.getLogger(__name__)


class AutomationDispatcher:
    def __init__(self, service, sender, *, interval=15):
        self.service, self.sender, self.interval = service, sender, interval
        self.task = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run(), name="nova-automations")

    async def run(self):
        while True:
            try:
                if self.sender.available():
                    await self.service.tick(self.sender)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("automation_poll_failed", extra={"error_type": type(error).__name__})
            await asyncio.sleep(self.interval)

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
