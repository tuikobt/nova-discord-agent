"""Optional AI configuration; an invalid AI setup never disables CRUD."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool = False
    key: str = field(default="", repr=False)
    model: str = ""
    daily_tokens: int = 100000
    daily_requests: int = 100
    output_tokens: int = 1500
    input_chars: int = 4000
    timeout: int = 60

    @classmethod
    def from_mapping(cls, values):
        try:
            config = cls(
                enabled=values.get("AI_ENABLED", "false").lower() == "true",
                key=values.get("OPENAI_API_KEY", "").strip(),
                model=values.get("OPENAI_MODEL", "").strip(),
                daily_tokens=int(values.get("AI_DAILY_TOKEN_LIMIT", "100000")),
                daily_requests=int(values.get("AI_DAILY_REQUEST_LIMIT", "100")),
            )
            if config.daily_tokens < 1 or config.daily_requests < 1:
                return cls()
            return config
        except (ValueError, TypeError):
            return cls()

    @property
    def ready(self):
        return self.enabled and bool(self.key and self.model)
