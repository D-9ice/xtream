from datetime import timedelta
from typing import Any
import json

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import CreditLedgerEntry, SubscriptionAccount, User, utc_now


def get_or_create_subscription(session: Session, user: User) -> SubscriptionAccount:
    subscription = session.exec(
        select(SubscriptionAccount).where(SubscriptionAccount.user_id == (user.id or 0))
    ).first()
    if subscription:
        return subscription
    subscription = SubscriptionAccount(
        user_id=user.id or 0,
        plan_name="free",
        status="active",
        credits_balance=1000,
        credits_reserved=0,
        credits_used_total=0,
        renewal_date=utc_now() + timedelta(days=30),
    )
    session.add(subscription)
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
    entry = CreditLedgerEntry(
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
    if subscription.status != "active":
        raise HTTPException(status_code=403, detail="subscription is not active")
    if subscription.credits_balance < amount:
        raise HTTPException(status_code=402, detail="insufficient credits")
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
    if subscription.status != "active":
        raise HTTPException(status_code=403, detail="subscription is not active")
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
