from __future__ import annotations

from app.config import DEFAULT_TENANT_ID


def current_tenant_id() -> str:
    # Phase 1 (single tenant): everything lives in one tenant/workspace.
    # Phase 2 will resolve this from token claims, subdomain, or an explicit header.
    return DEFAULT_TENANT_ID

