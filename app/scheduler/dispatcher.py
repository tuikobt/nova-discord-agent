import asyncio
import logging

from app.domain.reminder_delivery import DeliveryFailure
from app.services.reminder_delivery_service import ReminderDeliveryService

logger = logging.getLogger(__name__)


class ReminderDispatcher:
    def __init__(self, service, sender, *, interval=15):
        self.service, self.sender, self.interval = service, sender, interval
        self.deliveries = ReminderDeliveryService(service)
        self.task = None

    async def tick(self):
        actor = self.service.authorization.owner_id
        self.service.authorization.require_owner(actor)
        async with self.service.lock:
            await self.deliveries.enqueue(actor)
        for key in await self.deliveries.due(actor):
            async with self.service.lock:
                claim = await self.deliveries.claim(actor, key)
                if claim is None:
                    continue
                try:
                    message_id = await asyncio.wait_for(self.sender.send(claim), timeout=10)
                except TimeoutError:
                    logger.warning(
                        "reminder_delivery_failed",
                        extra={
                            "delivery_id": key,
                            "error_code": "timeout",
                            "attempt_count": claim.delivery.attempt_count,
                        },
                    )
                    await self.deliveries.finish(actor, claim, failure=DeliveryFailure("timeout"))
                except DeliveryFailure as error:
                    logger.warning(
                        "reminder_delivery_failed",
                        extra={
                            "delivery_id": key,
                            "error_code": error.code,
                            "attempt_count": claim.delivery.attempt_count,
                        },
                    )
                    await self.deliveries.finish(actor, claim, failure=error)
                except Exception:
                    logger.warning(
                        "reminder_delivery_failed",
                        extra={
                            "delivery_id": key,
                            "error_code": "unknown_error",
                            "attempt_count": claim.delivery.attempt_count,
                        },
                    )
                    await self.deliveries.finish(actor, claim, failure=DeliveryFailure())
                else:
                    # A failure here leaves the durable claim for lease recovery.
                    # Discord send and DB commit cannot be exactly-once.
                    await self.deliveries.finish(actor, claim, message_id=message_id)
                    logger.info(
                        "reminder_delivery_sent",
                        extra={"delivery_id": key, "attempt_count": claim.delivery.attempt_count},
                    )

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run(), name="nova-reminders")

    async def run(self):
        while True:
            try:
                if self.sender.available():
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("reminder_poll_failed", extra={"error_type": type(error).__name__})
            await asyncio.sleep(self.interval)

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
