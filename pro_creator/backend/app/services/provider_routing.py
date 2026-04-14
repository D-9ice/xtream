from app.config import (
    XAI_TEXT_MODEL,
    VIDEO_PROVIDER_DEFAULT,
    VOICE_PROVIDER_DEFAULT,
)


def resolve_script_route(plan_name: str | None) -> tuple[str, str]:
    return ("xai", XAI_TEXT_MODEL)


def resolve_image_provider() -> str:
    return "xai"


def resolve_voice_provider(requested_provider: str | None) -> str:
    return VOICE_PROVIDER_DEFAULT


def resolve_video_provider(requested_provider: str | None = None) -> str:
    return VIDEO_PROVIDER_DEFAULT
