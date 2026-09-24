from __future__ import annotations

import pytest
from sqlmodel import Session

from app.database import engine
from app.services import app_settings


DEFAULT_SETTINGS = {
    "auth_required": False,
    "plan_moderate_credits": 500,
    "plan_moderate_price_usd": 15,
    "plan_moderate_stripe_price_id": None,
    "plan_pro_credits": 2000,
    "plan_pro_price_usd": 49,
    "plan_pro_stripe_price_id": None,
    "plan_studio_credits": 6000,
    "plan_studio_price_usd": 119,
    "plan_studio_stripe_price_id": None,
    "factory_subscription_price_usd": 39,
    "factory_subscription_stripe_price_id": None,
    "owner_mode_enabled": False,
    "billing_receipts_live_mode": False,
    "free_character_slots": 100,
    "moderate_character_slots": 5,
    "pro_character_slots": 10,
    "studio_character_slots": 15,
    "character_slot_addon_size": 5,
    "character_slot_addon_cost_credits": 50,
}


def _apply_default_settings(session: Session) -> None:
    settings = app_settings.get_or_create_settings(session)
    for field, value in DEFAULT_SETTINGS.items():
        setattr(settings, field, value)
    session.add(settings)
    session.commit()


@pytest.fixture(autouse=True)
def reset_app_settings() -> None:
    with Session(engine) as session:
        _apply_default_settings(session)

    try:
        yield
    finally:
        with Session(engine) as session:
            _apply_default_settings(session)
