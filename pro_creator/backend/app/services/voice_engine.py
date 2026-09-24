import time

import requests

from app.config import (
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_TTS_VOICE_ID,
)
from app.storage import project_key, storage_client
from app.utils.file_manager import read_voice_profile_metadata
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _write_audio(
    project_id: str,
    scene_id: int,
    audio_bytes: bytes,
    extension: str = "wav",
    content_type: str = "audio/wav",
) -> str:
    key = project_key(project_id, f"audio/scene_{scene_id}.{extension}")
    storage_client.write_bytes(key, audio_bytes, content_type=content_type)
    return storage_client.public_url(key)


def _generate_with_xai_tts(text: str, voice_id: str | None) -> bytes:
    if not XAI_API_KEY.strip():
        raise RuntimeError("XAI_API_KEY is required for voice generation")
    payload = {
        "text": text,
        "voice_id": voice_id or XAI_TTS_VOICE_ID,
    }
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    last_error: Exception | str | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                f"{XAI_BASE_URL}/tts",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            if response.content:
                return response.content
            last_error = "xAI TTS returned an empty response"
        except Exception as exc:
            last_error = exc
            logger.warning("xAI TTS request error (attempt %s/%s): %s", attempt, attempts, exc)
        if attempt < attempts:
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"xAI TTS generation failed: {last_error}")


def clone_voice_profile(
    profile_name: str,
    sample_bytes: bytes,
    *,
    filename: str = "reference.wav",
    content_type: str = "audio/wav",
) -> dict:
    if not XAI_API_KEY.strip():
        raise RuntimeError("XAI_API_KEY is required for custom voice creation")
    if not sample_bytes:
        raise ValueError("Voice reference sample is empty")
    response = requests.post(
        f"{XAI_BASE_URL}/custom-voices",
        headers={"Authorization": f"Bearer {XAI_API_KEY}"},
        files={"file": (filename or "reference.wav", sample_bytes, content_type or "audio/wav")},
        data={"name": profile_name},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    voice_id = str(payload.get("voice_id") or "").strip()
    if not voice_id:
        raise RuntimeError("xAI custom voice creation did not return a voice_id")
    return {"provider": "xai", "voice_id": voice_id}


def generate_voice_for_scene(
    project_id: str,
    scene_id: int,
    text: str,
    voice_profile: str | None = None,
) -> dict:
    duration_seconds = max(2.0, len(text.split()) / 2.0)
    metadata = read_voice_profile_metadata(project_id)
    profile_data = metadata.get(voice_profile or "", {})
    voice_id = profile_data.get("voice_id") or XAI_TTS_VOICE_ID
    audio_bytes = _generate_with_xai_tts(text, voice_id)
    extension = "mp3"
    content_type = "audio/mpeg"
    audio_path = _write_audio(project_id, scene_id, audio_bytes, extension, content_type)
    logger.info("Generated voice for project %s scene %s", project_id, scene_id)
    return {
        "audio_path": audio_path,
        "duration_seconds": duration_seconds,
    }


def generate_voice(project_id: str, text: str, voice_profile: str) -> dict:
    return generate_voice_for_scene(project_id, 1, text, voice_profile)


def generate_voice_bytes(
    *,
    project_id: str,
    text: str,
    voice_profile: str | None = None,
    override_voice_id: str | None = None,
) -> tuple[bytes, str, str]:
    """
    Generate raw audio bytes without writing scene files.
    Returns: (audio_bytes, extension, content_type)
    """
    metadata = read_voice_profile_metadata(project_id)
    profile_data = metadata.get(voice_profile or "", {})
    voice_id = override_voice_id or profile_data.get("voice_id") or XAI_TTS_VOICE_ID
    return _generate_with_xai_tts(text, voice_id), "mp3", "audio/mpeg"
