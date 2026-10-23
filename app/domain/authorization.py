"""Configuration allowlist is authoritative, even if a user exists in the DB."""

from dataclasses import dataclass


class AuthorizationError(PermissionError):
    pass


class OwnerMismatchError(RuntimeError):
    """Prevent silently converting an existing owner's database to a new owner."""


@dataclass(frozen=True, slots=True)
class OwnerAuthorization:
    owner_id: int

    def is_owner(self, user_id: int) -> bool:
        return type(user_id) is int and user_id == self.owner_id

    def require_owner(self, user_id: int) -> None:
        if not self.is_owner(user_id):
            raise AuthorizationError("Chỉ chủ tài khoản được sử dụng NOVA.")
