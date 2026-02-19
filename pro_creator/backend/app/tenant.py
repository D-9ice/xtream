from __future__ import annotations

from contextvars import ContextVar, Token
import re

from app.config import DEFAULT_TENANT_ID

_TENANT_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_current_tenant: ContextVar[str] = ContextVar("current_tenant_id", default=DEFAULT_TENANT_ID)


def normalize_tenant_id(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return DEFAULT_TENANT_ID
    if not _TENANT_SLUG.match(value):
        return DEFAULT_TENANT_ID
    return value


def set_current_tenant_id(tenant_id: str | None) -> Token:
    return _current_tenant.set(normalize_tenant_id(tenant_id))


def reset_current_tenant_id(token: Token) -> None:
    _current_tenant.reset(token)


def current_tenant_id() -> str:
    # Phase 1 fallback remains DEFAULT_TENANT_ID; request middleware can override.
    return normalize_tenant_id(_current_tenant.get())
