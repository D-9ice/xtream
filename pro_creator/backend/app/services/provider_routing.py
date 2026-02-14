from app.config import (
    IMAGE_PROVIDER,
    OPENAI_MODEL_DRAFT,
    OPENAI_MODEL_PREMIUM,
    OPENAI_MODEL_STANDARD,
    SCRIPT_PROVIDER,
    VOICE_PROVIDER_DEFAULT,
)


def resolve_plan_tier(plan_name: str | None) -> str:
    plan = (plan_name or "free").strip().lower()
    if plan in {"enterprise", "business", "premium", "pro"}:
        return "premium"
    if plan in {"starter", "creator", "team", "standard"}:
        return "standard"
    return "draft"


def resolve_script_route(plan_name: str | None) -> tuple[str, str]:
    tier = resolve_plan_tier(plan_name)
    if tier == "premium":
        model = OPENAI_MODEL_PREMIUM
    elif tier == "standard":
        model = OPENAI_MODEL_STANDARD
    else:
        model = OPENAI_MODEL_DRAFT
    return (SCRIPT_PROVIDER, model)


def resolve_image_provider() -> str:
    return IMAGE_PROVIDER


def resolve_voice_provider(requested_provider: str | None) -> str:
    if requested_provider:
        return requested_provider.strip().lower()
    return VOICE_PROVIDER_DEFAULT
