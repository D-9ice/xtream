from datetime import timedelta
from typing import Any
import json

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import OWNER_EMAIL_ALLOWLIST
from app.models import CreditLedgerEntry, SubscriptionAccount, User, utc_now
from app.services.app_settings import get_or_create_settings
from app.tenant import current_tenant_id


def get_or_create_subscription(session: Session, user: User) -> SubscriptionAccount:
    tenant_id = current_tenant_id()
    subscription = session.exec(
        select(SubscriptionAccount).where(
            SubscriptionAccount.user_id == (user.id or 0),
            SubscriptionAccount.tenant_id == tenant_id,
        )
    ).first()
    if subscription:
        return subscription
    subscription = SubscriptionAccount(
        tenant_id=tenant_id,
        user_id=user.id or 0,
        plan_name="free",
        status="active",
        # New public accounts start with zero production credits. Owner access is
        # handled separately by has_owner_mode_access() and does not consume credits.
        credits_balance=0,
        credits_reserved=0,
        credits_used_total=0,
        factory_mode_status="inactive",
        factory_mode_access="none",
        renewal_date=utc_now() + timedelta(days=30),
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def has_owner_mode_access(session: Session, user: User) -> bool:
    settings = get_or_create_settings(session)
    if not settings.owner_mode_enabled:
        return False
    allowlist = {email.strip().lower() for email in OWNER_EMAIL_ALLOWLIST or [] if email.strip()}
    if allowlist:
        return (user.email or "").strip().lower() in allowlist
    return user.role == "admin"


def has_factory_mode_access(
    subscription: SubscriptionAccount,
    *,
    session: Session | None = None,
    user: User | None = None,
) -> bool:
    if session is not None and user is not None and has_owner_mode_access(session, user):
        return True
    if subscription.factory_mode_status != "active":
        return False
    if subscription.factory_mode_access == "subscription":
        if not subscription.factory_mode_renewal_date:
            return False
        return subscription.factory_mode_renewal_date > utc_now()
    return subscription.factory_mode_access == "one_time"


def grant_factory_mode_access(
    *,
    session: Session,
    user: User,
    access_mode: str,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    metadata: dict[str, Any] | None = None,
    renewal_days: int | None = None,
) -> SubscriptionAccount:
    normalized_access_mode = (access_mode or "").strip().lower()
    if normalized_access_mode not in {"one_time", "subscription"}:
        raise HTTPException(status_code=400, detail="access_mode must be one_time or subscription")
    subscription = get_or_create_subscription(session, user)
    subscription.factory_mode_status = "active"
    subscription.factory_mode_access = normalized_access_mode
    subscription.factory_mode_purchased_at = utc_now()
    subscription.factory_mode_renewal_date = (
        utc_now() + timedelta(days=max(1, int(renewal_days or 30)))
        if normalized_access_mode == "subscription"
        else None
    )
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="grant",
        amount=0,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def revoke_factory_mode_access(
    *,
    session: Session,
    user: User,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SubscriptionAccount:
    subscription = get_or_create_subscription(session, user)
    subscription.factory_mode_status = "inactive"
    subscription.factory_mode_access = "none"
    subscription.factory_mode_purchased_at = None
    subscription.factory_mode_renewal_date = None
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="revoke",
        amount=0,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def _append_ledger_entry(
    *,
    session: Session,
    user: User,
    subscription: SubscriptionAccount,
    kind: str,
    amount: int,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    tenant_id = current_tenant_id()
    entry = CreditLedgerEntry(
        tenant_id=tenant_id,
        user_id=user.id or 0,
        subscription_id=subscription.id or 0,
        kind=kind,
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        model=model,
        metadata_json=json.dumps(metadata) if metadata else None,
        balance_after=subscription.credits_balance,
        reserved_after=subscription.credits_reserved,
    )
    session.add(entry)


def reserve_credits(
    *,
    session: Session,
    user: User,
    amount: int,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SubscriptionAccount:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    subscription = get_or_create_subscription(session, user)
    owner_override = has_owner_mode_access(session, user)
    if not owner_override and subscription.status != "active":
        raise HTTPException(status_code=403, detail="subscription is not active")
    if not owner_override and subscription.credits_balance < amount:
        raise HTTPException(status_code=402, detail="insufficient credits")
    if not owner_override:
        subscription.credits_balance -= amount
        subscription.credits_reserved += amount
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="reserve",
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        model=model,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def consume_credits(
    *,
    session: Session,
    user: User,
    amount: int,
    from_reserved: bool = False,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SubscriptionAccount:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    subscription = get_or_create_subscription(session, user)
    owner_override = has_owner_mode_access(session, user)
    if not owner_override and subscription.status != "active":
        raise HTTPException(status_code=403, detail="subscription is not active")
    if not owner_override:
        if from_reserved:
            if subscription.credits_reserved < amount:
                raise HTTPException(status_code=402, detail="insufficient reserved credits")
            subscription.credits_reserved -= amount
        else:
            if subscription.credits_balance < amount:
                raise HTTPException(status_code=402, detail="insufficient credits")
            subscription.credits_balance -= amount
        subscription.credits_used_total += amount
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="consume",
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        model=model,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def refund_credits(
    *,
    session: Session,
    user: User,
    amount: int,
    to_reserved: bool = False,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SubscriptionAccount:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    subscription = get_or_create_subscription(session, user)
    if to_reserved:
        subscription.credits_reserved += amount
    else:
        subscription.credits_balance += amount
        subscription.credits_used_total = max(0, subscription.credits_used_total - amount)
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="refund",
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def expire_credits(
    *,
    session: Session,
    user: User,
    amount: int,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
) -> SubscriptionAccount:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    subscription = get_or_create_subscription(session, user)
    if subscription.credits_balance < amount:
        amount = subscription.credits_balance
    subscription.credits_balance -= amount
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="expire",
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def grant_credits(
    *,
    session: Session,
    user: User,
    amount: int,
    reason: str | None = None,
    action: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SubscriptionAccount:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    subscription = get_or_create_subscription(session, user)
    subscription.credits_balance += amount
    subscription.updated_at = utc_now()
    session.add(subscription)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="grant",
        amount=amount,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        model=model,
        metadata=metadata,
    )
    session.commit()
    session.refresh(subscription)
    return subscription


def record_usage_event(
    *,
    session: Session,
    user: User,
    action: str,
    reason: str | None = None,
    reference_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    subscription = get_or_create_subscription(session, user)
    _append_ledger_entry(
        session=session,
        user=user,
        subscription=subscription,
        kind="event",
        amount=0,
        reason=reason,
        action=action,
        reference_id=reference_id,
        provider=provider,
        model=model,
        metadata=metadata,
    )
    session.commit()
