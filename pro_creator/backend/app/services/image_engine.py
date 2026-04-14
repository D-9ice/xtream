import base64
import io
from typing import Any
import time

import requests

from app.config import (
    ENVIRONMENT,
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_IMAGE_MODEL,
)
from app.services.provider_routing import resolve_image_provider
from app.storage import project_key, storage_client
from app.utils.logger import get_logger

logger = get_logger(__name__)
ALLOW_LOCAL_PLACEHOLDERS = ENVIRONMENT != "production"


def _quality_image_prompt(prompt: str, style: str) -> str:
    base = (prompt or "").strip() or "cinematic scene"
    style_clean = (style or "cinematic").strip()
    return (
        f"{base}\n\n"
        f"Style direction: {style_clean}. "
        "Prioritize photorealistic detail, strong composition, crisp lighting, "
        "clean subject separation, and artifact-free output suitable for video production."
    )


def _extract_image_bytes(payload: dict[str, Any]) -> bytes | None:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    b64_image = first.get("b64_json") or first.get("image_base64")
    if isinstance(b64_image, str) and b64_image:
        return base64.b64decode(b64_image)

    url = first.get("url")
    if isinstance(url, str) and url:
        image_response = requests.get(url, timeout=60)
        image_response.raise_for_status()
        return image_response.content
    return None


def _generate_xai_image(prompt: str, style: str, scene_id: int = 1) -> bytes:
    api_key = XAI_API_KEY.strip()
    if not api_key:
        if ALLOW_LOCAL_PLACEHOLDERS:
            return _generate_local_placeholder(prompt, scene_id)
        raise RuntimeError("XAI_API_KEY is required for image generation in production")

    request_url = f"{XAI_BASE_URL}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": XAI_IMAGE_MODEL,
        "prompt": _quality_image_prompt(prompt, style),
        "response_format": "b64_json",
    }
    last_error: str | None = None
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(request_url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            body = response.json()
            image_bytes = _extract_image_bytes(body)
            if image_bytes:
                return image_bytes
            last_error = f"No image payload returned: {body}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    if ALLOW_LOCAL_PLACEHOLDERS:
        logger.warning("xAI image generation failed, falling back to local placeholder: %s", last_error)
        return _generate_local_placeholder(prompt, scene_id)
    raise RuntimeError(f"xAI image generation failed: {last_error}")


def _generate_local_placeholder(prompt: str, scene_id: int) -> bytes:
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (1024, 576), color=(18, 24, 38))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(40, 40), (984, 536)], outline=(34, 211, 238), width=3)
    title = f"Scene {scene_id}"
    subtitle = prompt[:80]
    draw.text((80, 80), title, fill=(226, 232, 240))
    draw.text((80, 140), subtitle, fill=(148, 163, 184))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_image_for_scene(
    project_id: str,
    scene_id: int,
    prompt: str,
    style: str,
    provider: str | None = None,
) -> dict:
    image_bytes, selected_provider = generate_image_bytes(
        prompt=prompt,
        style=style,
        scene_id=scene_id,
        provider=provider,
    )
    key = project_key(project_id, f"images/scene_{scene_id}.png")
    storage_client.write_bytes(key, image_bytes, content_type="image/png")
    logger.info(
        "Generated image for project %s scene %s using provider=%s",
        project_id,
        scene_id,
        selected_provider,
    )
    return {"image_path": storage_client.public_url(key)}


def generate_image_bytes(
    prompt: str,
    style: str,
    scene_id: int = 1,
    provider: str | None = None,
) -> tuple[bytes, str]:
    selected_provider = (provider or resolve_image_provider()).strip().lower()
    if selected_provider in {"xai", "grok"}:
        image_bytes = _generate_xai_image(prompt, style, scene_id=scene_id)
    else:
        if not ALLOW_LOCAL_PLACEHOLDERS:
            raise RuntimeError(f"Unsupported image provider in production: {selected_provider}")
        image_bytes = _generate_local_placeholder(prompt, scene_id)
    return image_bytes, selected_provider



def generate_image(project_id: str, prompt: str, style: str) -> dict:
    return generate_image_for_scene(project_id, 1, prompt, style)
