from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import CharacterProfile, SubscriptionAccount, User, utc_now
from app.services.app_settings import get_or_create_settings
from app.services.credits import consume_credits, get_or_create_subscription, has_owner_mode_access
from app.tenant import current_tenant_id


def _plan_base_character_slots(subscription: SubscriptionAccount, *, session: Session) -> int:
    settings = get_or_create_settings(session)
    plan_name = (subscription.plan_name or "").strip().lower()
    if plan_name == "moderate":
        return max(0, int(settings.moderate_character_slots))
    if plan_name == "pro":
        return max(0, int(settings.pro_character_slots))
    if plan_name == "studio":
        return max(0, int(settings.studio_character_slots))
    return max(0, int(settings.free_character_slots))


def count_character_library_usage(session: Session) -> int:
    tenant_id = current_tenant_id()
    return len(
        session.exec(
            select(CharacterProfile.id).where(CharacterProfile.tenant_id == tenant_id)
        ).all()
    )


def build_character_slot_summary(
    *,
    session: Session,
    subscription: SubscriptionAccount,
) -> dict[str, int | bool]:
    settings = get_or_create_settings(session)
    used = count_character_library_usage(session)
    base_slots = _plan_base_character_slots(subscription, session=session)
    extra_slots = max(0, int(subscription.extra_character_slots or 0))
    total_slots = base_slots + extra_slots
    remaining_slots = max(0, total_slots - used)
    addon_pack_size = max(1, int(settings.character_slot_addon_size))
    addon_pack_cost_credits = max(1, int(settings.character_slot_addon_cost_credits))
    return {
        "base_slots": base_slots,
        "extra_slots": extra_slots,
        "total_slots": total_slots,
        "used_slots": used,
        "remaining_slots": remaining_slots,
        "addon_pack_size": addon_pack_size,
        "addon_pack_cost_credits": addon_pack_cost_credits,
        "is_full": remaining_slots <= 0,
    }


def get_character_slot_summary(
    *,
    session: Session,
    user: User,
) -> dict[str, int | bool]:
    subscription = get_or_create_subscription(session, user)
    return build_character_slot_summary(session=session, subscription=subscription)


def ensure_character_slot_available(
    *,
    session: Session,
    user: User,
) -> dict[str, int | bool]:
    if has_owner_mode_access(session, user):
        return get_character_slot_summary(session=session, user=user)
    summary = get_character_slot_summary(session=session, user=user)
    if bool(summary["remaining_slots"]):
        return summary
    raise HTTPException(
        status_code=402,
        detail=(
            "Character library is full for your current plan. "
            "Upgrade the plan or buy another character slot pack."
        ),
    )


def purchase_character_slot_pack(
    *,
    session: Session,
    user: User,
    pack_count: int = 1,
) -> SubscriptionAccount:
    clean_pack_count = int(pack_count)
    if clean_pack_count <= 0:
        raise HTTPException(status_code=400, detail="pack_count must be greater than 0")
    settings = get_or_create_settings(session)
    subscription = get_or_create_subscription(session, user)
    addon_pack_size = max(1, int(settings.character_slot_addon_size))
    addon_pack_cost_credits = max(1, int(settings.character_slot_addon_cost_credits))
    total_cost = addon_pack_cost_credits * clean_pack_count
    total_slots = addon_pack_size * clean_pack_count
    subscription = consume_credits(
        session=session,
        user=user,
        amount=total_cost,
        reason=f"character slot add-on x{clean_pack_count}",
        action="billing.character_slots.purchase",
        reference_id=user.email,
        metadata={
            "pack_count": clean_pack_count,
            "pack_size": addon_pack_size,
            "granted_slots": total_slots,
            "cost_credits": total_cost,
        },
    )
    subscription.extra_character_slots += total_slots
    subscription.updated_at = utc_now()
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription
