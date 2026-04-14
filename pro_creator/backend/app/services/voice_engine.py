import io
import math
import time
import wave

import requests

from app.config import (
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_TTS_VOICE_ID,
    TTS_PROVIDER,
)
from app.storage import project_key, storage_client
from app.utils.file_manager import read_voice_profile_metadata
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _write_tone(duration_seconds: float) -> bytes:
    sample_rate = 22050
    total_frames = int(duration_seconds * sample_rate)
    amplitude = 16000
    frequency = 440.0

    buffer = io.BytesIO()
    with wave.open(buffer, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(total_frames):
            value = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav_file.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))
    return buffer.getvalue()


def _resolve_provider(provider: str | None) -> str:
    if provider:
        return provider.lower()
    return TTS_PROVIDER.lower()


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
        return _write_tone(max(2.0, len(text.split()) / 2.0))
    payload = {
        "text": text,
        "voice_id": voice_id or XAI_TTS_VOICE_ID,
    }
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
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
            if response.ok and response.content:
                return response.content
            logger.warning("xAI TTS request failed (attempt %s/%s): %s", attempt, attempts, response.text)
        except Exception as exc:
            logger.warning("xAI TTS request error (attempt %s/%s): %s", attempt, attempts, exc)
        if attempt < attempts:
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    return _write_tone(max(2.0, len(text.split()) / 2.0))


def clone_voice_profile(profile_name: str, sample_bytes: bytes, provider: str | None) -> dict:
    _resolve_provider(provider)
    return {"provider": "xai"}


def generate_voice_for_scene(
    project_id: str,
    scene_id: int,
    text: str,
    voice_profile: str | None = None,
    provider: str | None = None,
) -> dict:
    duration_seconds = max(2.0, len(text.split()) / 2.0)
    metadata = read_voice_profile_metadata(project_id)
    profile_data = metadata.get(voice_profile or "", {})
    voice_id = profile_data.get("voice_id") or XAI_TTS_VOICE_ID
    audio_bytes = _generate_with_xai_tts(text, voice_id)
    extension = "mp3"
    content_type = "audio/mpeg"
    if not audio_bytes:
        audio_bytes = _write_tone(duration_seconds)
    audio_path = _write_audio(project_id, scene_id, audio_bytes, extension, content_type)
    logger.info("Generated voice for project %s scene %s", project_id, scene_id)
    return {
        "audio_path": audio_path,
        "duration_seconds": duration_seconds,
    }


def generate_voice(project_id: str, text: str, voice_profile: str, provider: str | None) -> dict:
    return generate_voice_for_scene(project_id, 1, text, voice_profile, provider)


def generate_voice_bytes(
    *,
    project_id: str,
    text: str,
    voice_profile: str | None = None,
    provider: str | None = None,
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
