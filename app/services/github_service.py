"""Owner-scoped reads fenced before HTTP, after HTTP and after queued waits."""

import asyncio

from app.db.base import utc_now
from app.domain.errors import DomainError, ValidationError
from app.integrations.errors import IntegrationError
from app.services.core_service import CoreService


class GitHubService(CoreService):
    def __init__(self, connections, reader, *, clock=utc_now):
        super().__init__(connections.sessions, connections.authorization)
        self.connections, self.reader, self.clock = connections, reader, clock

    async def read(self, actor, key, repo, operation, *, expected_version, **options):
        self.authorize(actor)
        record = await self.connections.get(actor, key)
        if record["provider"] != "github":
            raise ValidationError("Kết nối này không phải GitHub.")
        if self.connections.secrets.contains(repo) or self.connections.secrets.contains(
            options.get("path")
        ):
            raise ValidationError("Không nhập token/key trong repo hoặc đường dẫn tài liệu.")

        async def authorize(resource):
            return await self.connections.authorize_resource(
                actor, key, resource, expected_version=expected_version
            )

        scope = await authorize(repo)
        token = self.connections.credentials.resolve("github")
        if not token:
            raise IntegrationError("missing_credential")
        try:
            async with asyncio.timeout(15):
                result = await self.reader.read(
                    scope["resource"], operation, token=token, authorize=authorize, **options
                )
                await authorize(scope["resource"])
        except TimeoutError:
            raise IntegrationError("timeout") from None
        except DomainError:
            raise
        except Exception:
            raise IntegrationError("unknown_error") from None
        return self.connections.secrets.redact(
            dict(
                **result,
                connection_id=key,
                connection_version=expected_version,
                retrieved_at=self.clock().isoformat(),
                untrusted=True,
            )
        )
