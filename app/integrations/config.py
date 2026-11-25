"""Only these credentials can be resolved for external connections."""

from dataclasses import dataclass, field

CREDENTIAL_REFS = {"github": "GITHUB_READ_TOKEN", "notion": "NOTION_READ_TOKEN"}


@dataclass(frozen=True)
class ConnectionCredentials:
    github: str = field(default="", repr=False)
    notion: str = field(default="", repr=False)

    @classmethod
    def from_mapping(cls, values):
        selected = {}
        for provider, name in CREDENTIAL_REFS.items():
            value = values.get(name, "")
            value = value.strip() if isinstance(value, str) else ""
            selected[provider] = (
                value if value != "replace-me" and not any(c.isspace() for c in value) else ""
            )
        return cls(**selected)

    def resolve(self, provider):
        if provider not in CREDENTIAL_REFS:
            raise ValueError("Unsupported credential reference")
        return getattr(self, provider)

    def registered(self):
        return tuple(value for value in (self.github, self.notion) if value)
