from __future__ import annotations

from sqlmodel import Session, select

from app.config import (
    FACTORY_MODE_ONE_TIME_PRICE_USD,
    FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID,
    FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS,
    FACTORY_MODE_SUBSCRIPTION_PRICE_USD,
    FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID,
    PAYSTACK_SECRET_KEY,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from app.models import AppSettings, utc_now

PLAN_NAMES = ("moderate", "pro", "studio")
PLAN_LABELS = {
    "moderate": "Moderate",
    "pro": "Pro",
    "studio": "Studio",
}
FACTORY_PLAN_LABELS = {
    "factory_one_time": "Factory Mode One-Time",
    "factory_subscription": "Factory Mode Subscription",
}


def _clean_non_negative_int(value: int, *, field_name: str, minimum: int = 0) -> int:
    clean_value = int(value)
    if clean_value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return clean_value


def _clean_optional_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def get_or_create_settings(session: Session) -> AppSettings:
    settings = session.exec(select(AppSettings).where(AppSettings.id == 1)).first()
    if settings:
        return settings
    settings = AppSettings(
        id=1,
        auth_required=False,
        factory_one_time_price_usd=FACTORY_MODE_ONE_TIME_PRICE_USD,
        factory_one_time_stripe_price_id=FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID or None,
        factory_subscription_price_usd=FACTORY_MODE_SUBSCRIPTION_PRICE_USD,
        factory_subscription_stripe_price_id=FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID or None,
        owner_mode_enabled=False,
        billing_receipts_live_mode=False,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def set_auth_required(session: Session, enabled: bool) -> AppSettings:
    settings = get_or_create_settings(session)
    settings.auth_required = bool(enabled)
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def get_plan_settings_payload(settings: AppSettings) -> list[dict[str, object]]:
    stripe_ready = bool(STRIPE_SECRET_KEY.strip() and STRIPE_WEBHOOK_SECRET.strip())
    paystack_ready = bool(PAYSTACK_SECRET_KEY.strip())

    def checkout_providers(stripe_price_id: str | None) -> list[str]:
        providers: list[str] = []
        if stripe_price_id and stripe_ready:
            providers.append("stripe")
        if paystack_ready:
            providers.append("paystack")
        return providers

    return [
        {
            "id": "moderate",
            "name": PLAN_LABELS["moderate"],
            "kind": "credits",
            "credits": settings.plan_moderate_credits,
            "price_usd": settings.plan_moderate_price_usd,
            "stripe_price_id": settings.plan_moderate_stripe_price_id,
            "base_character_slots": settings.moderate_character_slots,
            "checkout_providers": checkout_providers(settings.plan_moderate_stripe_price_id),
        },
        {
            "id": "pro",
            "name": PLAN_LABELS["pro"],
            "kind": "credits",
            "credits": settings.plan_pro_credits,
            "price_usd": settings.plan_pro_price_usd,
            "stripe_price_id": settings.plan_pro_stripe_price_id,
            "base_character_slots": settings.pro_character_slots,
            "checkout_providers": checkout_providers(settings.plan_pro_stripe_price_id),
        },
        {
            "id": "studio",
            "name": PLAN_LABELS["studio"],
            "kind": "credits",
            "credits": settings.plan_studio_credits,
            "price_usd": settings.plan_studio_price_usd,
            "stripe_price_id": settings.plan_studio_stripe_price_id,
            "base_character_slots": settings.studio_character_slots,
            "checkout_providers": checkout_providers(settings.plan_studio_stripe_price_id),
        },
        {
            "id": "factory_one_time",
            "name": FACTORY_PLAN_LABELS["factory_one_time"],
            "kind": "factory_access",
            "access_mode": "one_time",
            "access_days": None,
            "description": "Unlimited autonomous production access without expiration.",
            "credits": 0,
            "price_usd": settings.factory_one_time_price_usd,
            "stripe_price_id": settings.factory_one_time_stripe_price_id,
            "base_character_slots": 0,
            "checkout_providers": checkout_providers(settings.factory_one_time_stripe_price_id),
        },
        {
            "id": "factory_subscription",
            "name": FACTORY_PLAN_LABELS["factory_subscription"],
            "kind": "factory_access",
            "access_mode": "subscription",
            "access_days": FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS,
            "description": "Autonomous production access that renews every billing cycle.",
            "credits": 0,
            "price_usd": settings.factory_subscription_price_usd,
            "stripe_price_id": settings.factory_subscription_stripe_price_id,
            "base_character_slots": 0,
            "checkout_providers": checkout_providers(settings.factory_subscription_stripe_price_id),
        },
    ]


def get_character_slot_policy_payload(settings: AppSettings) -> dict[str, int]:
    return {
        "free_base_slots": settings.free_character_slots,
        "addon_pack_size": settings.character_slot_addon_size,
        "addon_pack_cost_credits": settings.character_slot_addon_cost_credits,
    }


def update_billing_settings(
    session: Session,
    *,
    moderate_credits: int,
    moderate_price_usd: int,
    moderate_base_character_slots: int,
    moderate_stripe_price_id: str | None,
    pro_credits: int,
    pro_price_usd: int,
    pro_base_character_slots: int,
    pro_stripe_price_id: str | None,
    studio_credits: int,
    studio_price_usd: int,
    studio_base_character_slots: int,
    studio_stripe_price_id: str | None,
    factory_one_time_price_usd: int,
    factory_one_time_stripe_price_id: str | None,
    factory_subscription_price_usd: int,
    factory_subscription_stripe_price_id: str | None,
    owner_mode_enabled: bool,
    receipts_live_mode: bool,
    free_base_character_slots: int,
    character_slot_addon_size: int,
    character_slot_addon_cost_credits: int,
) -> AppSettings:
    settings = get_or_create_settings(session)
    settings.plan_moderate_credits = _clean_non_negative_int(moderate_credits, field_name="moderate credits", minimum=1)
    settings.plan_moderate_price_usd = _clean_non_negative_int(
        moderate_price_usd,
        field_name="moderate price",
        minimum=0,
    )
    settings.moderate_character_slots = _clean_non_negative_int(
        moderate_base_character_slots,
        field_name="moderate base character slots",
        minimum=1,
    )
    settings.plan_moderate_stripe_price_id = _clean_optional_text(moderate_stripe_price_id)

    settings.plan_pro_credits = _clean_non_negative_int(pro_credits, field_name="pro credits", minimum=1)
    settings.plan_pro_price_usd = _clean_non_negative_int(pro_price_usd, field_name="pro price", minimum=0)
    settings.pro_character_slots = _clean_non_negative_int(
        pro_base_character_slots,
        field_name="pro base character slots",
        minimum=1,
    )
    settings.plan_pro_stripe_price_id = _clean_optional_text(pro_stripe_price_id)

    settings.plan_studio_credits = _clean_non_negative_int(studio_credits, field_name="studio credits", minimum=1)
    settings.plan_studio_price_usd = _clean_non_negative_int(
        studio_price_usd,
        field_name="studio price",
        minimum=0,
    )
    settings.studio_character_slots = _clean_non_negative_int(
        studio_base_character_slots,
        field_name="studio base character slots",
        minimum=1,
    )
    settings.plan_studio_stripe_price_id = _clean_optional_text(studio_stripe_price_id)

    settings.factory_one_time_price_usd = _clean_non_negative_int(
        factory_one_time_price_usd,
        field_name="factory one-time price",
        minimum=0,
    )
    settings.factory_one_time_stripe_price_id = _clean_optional_text(factory_one_time_stripe_price_id)

    settings.factory_subscription_price_usd = _clean_non_negative_int(
        factory_subscription_price_usd,
        field_name="factory subscription price",
        minimum=0,
    )
    settings.factory_subscription_stripe_price_id = _clean_optional_text(factory_subscription_stripe_price_id)
    settings.owner_mode_enabled = bool(owner_mode_enabled)
    settings.billing_receipts_live_mode = bool(receipts_live_mode)

    settings.free_character_slots = _clean_non_negative_int(
        free_base_character_slots,
        field_name="free base character slots",
        minimum=0,
    )
    settings.character_slot_addon_size = _clean_non_negative_int(
        character_slot_addon_size,
        field_name="character slot add-on size",
        minimum=1,
    )
    settings.character_slot_addon_cost_credits = _clean_non_negative_int(
        character_slot_addon_cost_credits,
        field_name="character slot add-on cost",
        minimum=1,
    )
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
