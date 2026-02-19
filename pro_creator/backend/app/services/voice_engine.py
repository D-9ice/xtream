import base64
import io
import math
import time
import wave

import requests

from app.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_VOICE_ID,
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    TTS_PROVIDER,
    XTTS_ENDPOINT,
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


def _generate_with_elevenlabs(text: str, voice_id: str | None) -> bytes:
    if not ELEVENLABS_API_KEY or not voice_id:
        logger.warning("ElevenLabs not configured, using tone fallback")
        return _write_tone(max(2.0, len(text.split()) / 2.0))
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.75,
        },
    }
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.ok:
                return response.content
            logger.warning("ElevenLabs request failed (attempt %s/%s): %s", attempt, attempts, response.text)
        except Exception as exc:
            logger.warning("ElevenLabs request error (attempt %s/%s): %s", attempt, attempts, exc)
        if attempt < attempts:
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    return _write_tone(max(2.0, len(text.split()) / 2.0))


def _generate_with_xtts(text: str, speaker_wav_b64: str | None) -> bytes:
    if not XTTS_ENDPOINT:
        logger.warning("XTTS endpoint not configured, using tone fallback")
        return _write_tone(max(2.0, len(text.split()) / 2.0))
    payload = {
        "text": text,
        "speaker_wav": speaker_wav_b64,
        "language": "en",
    }
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(XTTS_ENDPOINT, json=payload, timeout=60)
            if not response.ok:
                logger.warning("XTTS request failed (attempt %s/%s): %s", attempt, attempts, response.text)
            else:
                if response.headers.get("content-type", "").startswith("application/json"):
                    data = response.json()
                    audio_b64 = data.get("audio") or data.get("wav")
                    if audio_b64:
                        return base64.b64decode(audio_b64)
                return response.content
        except Exception as exc:
            logger.warning("XTTS request error (attempt %s/%s): %s", attempt, attempts, exc)
        if attempt < attempts:
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    return _write_tone(max(2.0, len(text.split()) / 2.0))


def clone_voice_profile(profile_name: str, sample_bytes: bytes, provider: str | None) -> dict:
    resolved_provider = _resolve_provider(provider)
    if resolved_provider != "elevenlabs":
        return {"provider": resolved_provider}
    if not ELEVENLABS_API_KEY:
        logger.warning("ElevenLabs API key missing, skipping voice clone")
        return {"provider": resolved_provider}
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    files = {
        "files": ("sample.wav", sample_bytes, "audio/wav"),
    }
    data = {
        "name": profile_name,
        "description": "Pro Creator voice clone",
    }
    response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
    if not response.ok:
        logger.warning("ElevenLabs clone failed: %s", response.text)
        return {"provider": resolved_provider}
    payload = response.json()
    return {
        "provider": resolved_provider,
        "voice_id": payload.get("voice_id"),
    }


def generate_voice_for_scene(
    project_id: str,
    scene_id: int,
    text: str,
    voice_profile: str | None = None,
    provider: str | None = None,
) -> dict:
    duration_seconds = max(2.0, len(text.split()) / 2.0)
    metadata = read_voice_profile_metadata(project_id)
    resolved_provider = _resolve_provider(provider)
    profile_data = metadata.get(voice_profile or "", {})
    audio_bytes = None
    extension = "wav"
    content_type = "audio/wav"
    if resolved_provider == "elevenlabs":
        voice_id = profile_data.get("voice_id") or ELEVENLABS_VOICE_ID
        audio_bytes = _generate_with_elevenlabs(text, voice_id)
        extension = "mp3"
        content_type = "audio/mpeg"
    else:
        speaker_key = profile_data.get("sample_key")
        speaker_b64 = None
        if speaker_key and storage_client.exists(speaker_key):
            speaker_b64 = base64.b64encode(storage_client.read_bytes(speaker_key)).decode("utf-8")
        audio_bytes = _generate_with_xtts(text, speaker_b64)
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
