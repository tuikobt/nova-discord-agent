"""Credential filtering shared by the AI boundary, logs and local Git checks.

Patterns are a backstop, not a promise to recognize every kind of credential.
Authorization and approval never depend on hiding the system prompt.
"""

import re

SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"),
    "discord_token": re.compile(
        r"\b(?:mfa\.[A-Za-z0-9_-]{60,}|"
        r"[A-Za-z0-9_-]{20,30}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})\b"
    ),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*"),
}


class SecretFilter:
    def __init__(self, secrets=()):
        self._values = tuple(
            sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True)
        )

    def contains(self, value):
        return isinstance(value, str) and (
            any(secret in value for secret in self._values)
            or any(pattern.search(value) for pattern in SECRET_PATTERNS.values())
        )

    def redact(self, value):
        if isinstance(value, str):
            for secret in self._values:
                value = value.replace(secret, "[REDACTED]")
            for pattern in SECRET_PATTERNS.values():
                value = pattern.sub("[REDACTED]", value)
            return value
        if isinstance(value, dict):
            return {self.redact(key): self.redact(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        return value
