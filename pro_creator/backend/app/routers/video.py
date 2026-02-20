from datetime import datetime
import io
import shutil
import subprocess
import tempfile

from fastapi import APIRouter, Query, Depends, HTTPException
from PIL import Image, ImageDraw
from sqlmodel import Session

import requests
from pathlib import Path

from app.auth import get_current_user
from app.config import (
    CREDITS_COST_THUMBNAIL_AI_GENERATE,
    CREDITS_COST_THUMBNAIL_GENERATE,
    CREDITS_COST_VIDEO_EXPORT,
    CREDITS_COST_VIDEO_RENDER,
    OPENAI_API_KEY,
    PROJECTS_DIR,
)
from app.database import get_session
from app.models import User
from app.services.credits import consume_credits, record_usage_event
from app.services.image_engine import generate_image_bytes
from app.storage import project_key, storage_client
from app.schemas import (
    EditByTextRequest,
    EditByTextResponse,
    ExportBatchRequest,
    ExportBatchResponse,
    ExportPresetRequest,
    ExportPresetResponse,
    ExportStatusEntry,
    ExportStatusResponse,
    FeatureStubResponse,
    ThumbnailGenerateRequest,
    ThumbnailGenerateResponse,
    ThumbnailSetPrimaryRequest,
    ThumbnailVariantResponse,
    VideoImportRequest,
    VideoImportResponse,
    VideoRequest,
    VideoResponse,
)
from app.services.video_engine import render_video
from app.services.lipsync_engine import fallback_segments, generate_lipsync
from app.utils.file_manager import read_json_artifact, read_scene_metadata, write_json_artifact
from app.utils.logger import get_logger

router = APIRouter(
    prefix="/video",
    tags=["Video"],
    dependencies=[Depends(get_current_user)],
)
logger = get_logger(__name__)

_THUMBNAIL_EXTENSIONS = ("png", "jpg", "jpeg")


def _find_scene_image_key(project_id: str, scene_id: int) -> str | None:
    preferred = project_key(project_id, f"images/scene_{scene_id}.png")
    if storage_client.exists(preferred):
        return preferred
    fallback = project_key(project_id, "images/scene_1.png")
    if storage_client.exists(fallback):
        return fallback
    for key in storage_client.list_keys(f"{project_id}/images/"):
        if key.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            return key
    return None


def _load_video_frame(
    project_id: str,
    timestamp_seconds: float,
) -> Image.Image | None:
    source_candidates = [
        project_key(project_id, "video/final.mp4"),
        project_key(project_id, "video/imported.mp4"),
    ]
    source_key = next((key for key in source_candidates if storage_client.exists(key)), None)
    if not source_key:
        return None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise ValueError("ffmpeg is required for video-based thumbnail generation.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_thumbnail_") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = temp_path / "source.mp4"
        frame_path = temp_path / "frame.png"
        source_path.write_bytes(storage_client.read_bytes(source_key))
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-ss",
                str(max(0.0, timestamp_seconds)),
                "-i",
                str(source_path),
                "-frames:v",
                "1",
                str(frame_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        if not frame_path.exists():
            return None
        return Image.open(frame_path).convert("RGB")


def _load_thumbnail_base(
    project_id: str,
    source: str,
    scene_id: int,
    timestamp_seconds: float,
) -> tuple[Image.Image, str]:
    source_mode = source.lower().strip()
    if source_mode not in {"auto", "video", "image"}:
        raise ValueError("source must be one of: auto, video, image")

    if source_mode in {"auto", "video"}:
        try:
            frame = _load_video_frame(project_id, timestamp_seconds)
        except Exception:
            if source_mode == "video":
                raise
            frame = None
        if frame is not None:
            return frame, "video"
        if source_mode == "video":
            raise ValueError("No source video found. Render or import a video first.")

    image_key = _find_scene_image_key(project_id, scene_id)
    if not image_key:
        raise ValueError(
            "No source media found. Generate images or render/import a video first."
        )
    image_bytes = storage_client.read_bytes(image_key)
    if not image_bytes:
        raise ValueError("Source image exists but is empty.")
    return Image.open(io.BytesIO(image_bytes)).convert("RGB"), "image"


def _build_ai_thumbnail_prompt(
    payload: ThumbnailGenerateRequest,
    variant_id: int = 1,
    variant_count: int = 1,
) -> str:
    title = (payload.title or "").strip()
    subtitle = (payload.subtitle or "").strip()
    custom = (payload.ai_prompt or "").strip()
    base_lines = [
        "Design a high-converting social-media video thumbnail.",
        "Prioritize bold composition, clean focal subject, strong contrast, and platform-ready clarity.",
    ]
    if title:
        base_lines.append(f"Primary headline to support: {title}")
    if subtitle:
        base_lines.append(f"Secondary subheadline to support: {subtitle}")
    if custom:
        base_lines.append(f"Creative direction: {custom}")
    if variant_count > 1:
        base_lines.append(
            f"Create variation {variant_id}/{variant_count} with a distinct composition and focal framing."
        )
    base_lines.append(
        f"Target aspect ratio {payload.width}:{payload.height}. Avoid watermarks, logos, and unreadable tiny text."
    )
    return "\n".join(base_lines)


def _generate_ai_thumbnail_base(
    payload: ThumbnailGenerateRequest,
    variant_id: int = 1,
    variant_count: int = 1,
) -> tuple[Image.Image, str]:
    prompt = _build_ai_thumbnail_prompt(payload, variant_id=variant_id, variant_count=variant_count)
    preferred_provider = "openai" if OPENAI_API_KEY.strip() else "local"
    image_bytes, provider_used = generate_image_bytes(
        prompt=prompt,
        style=payload.style,
        scene_id=max(1, payload.scene_id),
        provider=preferred_provider,
    )
    if not image_bytes:
        raise ValueError("AI thumbnail generation returned empty image bytes.")
    return Image.open(io.BytesIO(image_bytes)).convert("RGB"), provider_used


def _cover_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    width = max(64, min(width, 3840))
    height = max(64, min(height, 3840))
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        raise ValueError("Invalid source image dimensions.")
    scale = max(width / src_w, height / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = [word for word in text.split() if word]
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _apply_text_overlay(
    image: Image.Image,
    title: str | None,
    subtitle: str | None,
) -> Image.Image:
    title_text = (title or "").strip()
    subtitle_text = (subtitle or "").strip()
    if not title_text and not subtitle_text:
        return image

    canvas = image.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size

    overlay_height = int(height * 0.38)
    overlay_top = max(0, height - overlay_height)
    draw.rectangle(
        [(0, overlay_top), (width, height)],
        fill=(8, 10, 26, 190),
    )

    max_title_chars = max(24, width // 24)
    max_subtitle_chars = max(28, width // 28)
    title_lines = _wrap_text(title_text[:220], max_title_chars)[:3]
    subtitle_lines = _wrap_text(subtitle_text[:320], max_subtitle_chars)[:3]

    y = overlay_top + int(height * 0.05)
    x = int(width * 0.05)
    for line in title_lines:
        draw.text((x, y), line, fill=(242, 248, 255, 255))
        y += 28
    if title_lines and subtitle_lines:
        y += 10
    for line in subtitle_lines:
        draw.text((x, y), line, fill=(184, 201, 219, 255))
        y += 22

    return canvas.convert("RGB")


@router.post("/render", response_model=VideoResponse)
def render_video_endpoint(
    payload: VideoRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VideoResponse:
    try:
        result = render_video(payload.project_id, render_provider=payload.render_provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    provider_label = (payload.render_provider or "ffmpeg").strip().lower()
    model_label = "ffmpeg"
    if provider_label == "runway_gen4_turbo":
        model_label = "gen4_turbo"
    elif provider_label == "runway_gen4_5":
        model_label = "gen4.5"
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_VIDEO_RENDER,
        reason="video render",
        action="video.render",
        reference_id=payload.project_id,
        provider="runway" if provider_label.startswith("runway_") else "local",
        model=model_label,
    )
    logger.info(
        "Rendered video for project %s provider=%s model=%s",
        payload.project_id,
        provider_label,
        model_label,
    )
    return VideoResponse(**result)


@router.post("/thumbnail/generate", response_model=ThumbnailGenerateResponse)
def generate_thumbnail_endpoint(
    payload: ThumbnailGenerateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ThumbnailGenerateResponse:
    output_format = payload.format.lower().strip()
    mode = payload.mode.lower().strip()
    variant_count = max(1, min(payload.variant_count, 4))
    if output_format not in _THUMBNAIL_EXTENSIONS:
        raise HTTPException(status_code=400, detail="format must be png or jpg")
    if mode not in {"classic", "ai"}:
        raise HTTPException(status_code=400, detail="mode must be classic or ai")
    if mode == "classic" and variant_count > 1:
        raise HTTPException(
            status_code=400,
            detail="variant_count > 1 is supported only in ai mode",
        )
    variants: list[ThumbnailVariantResponse] = []
    first_key: str | None = None
    first_source_used = ""
    try:
        for variant_id in range(1, variant_count + 1):
            if mode == "ai":
                base_image, ai_provider = _generate_ai_thumbnail_base(
                    payload,
                    variant_id=variant_id,
                    variant_count=variant_count,
                )
                source_used = f"ai:{ai_provider}"
            else:
                base_image, source_used = _load_thumbnail_base(
                    payload.project_id,
                    payload.source,
                    payload.scene_id,
                    payload.timestamp_seconds,
                )
            sized = _cover_resize(base_image, payload.width, payload.height)
            with_text = _apply_text_overlay(sized, payload.title, payload.subtitle)

            buffer = io.BytesIO()
            if output_format in {"jpg", "jpeg"}:
                with_text.save(buffer, format="JPEG", quality=92, optimize=True)
                ext = "jpg"
                content_type = "image/jpeg"
            else:
                with_text.save(buffer, format="PNG", optimize=True)
                ext = "png"
                content_type = "image/png"

            key_suffix = "thumbnail_latest" if variant_count == 1 else f"thumbnail_v{variant_id}"
            key = project_key(payload.project_id, f"thumbnails/{key_suffix}.{ext}")
            storage_client.write_bytes(key, buffer.getvalue(), content_type=content_type)
            if first_key is None:
                first_key = key
                first_source_used = source_used
            variants.append(
                ThumbnailVariantResponse(
                    variant_id=variant_id,
                    thumbnail_key=key,
                    thumbnail_path=storage_client.public_url(key),
                    source_used=source_used,
                    width=payload.width,
                    height=payload.height,
                )
            )

        if first_key and variant_count > 1:
            latest_key = project_key(payload.project_id, f"thumbnails/thumbnail_latest.{ext}")
            storage_client.write_bytes(
                latest_key,
                storage_client.read_bytes(first_key),
                content_type=content_type,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Thumbnail generation failed: {exc}") from exc

    consume_credits(
        session=session,
        user=current_user,
        amount=(
            CREDITS_COST_THUMBNAIL_AI_GENERATE
            if mode == "ai"
            else CREDITS_COST_THUMBNAIL_GENERATE
        )
        * variant_count,
        reason="thumbnail generation",
        action="thumbnail.generate.ai" if mode == "ai" else "thumbnail.generate",
        reference_id=payload.project_id,
        provider=(first_source_used.split(":", 1)[-1] if mode == "ai" else "local"),
        model=first_source_used if mode == "ai" else payload.source,
        metadata={
            "mode": mode,
            "source": first_source_used,
            "format": ext,
            "width": payload.width,
            "height": payload.height,
            "style": payload.style,
            "variant_count": variant_count,
        },
    )
    logger.info(
        "Generated %s thumbnail(s) for project %s using %s source (variants=%s)",
        mode,
        payload.project_id,
        first_source_used,
        variant_count,
    )
    if not variants:
        raise HTTPException(status_code=502, detail="No thumbnail variants were generated.")
    return ThumbnailGenerateResponse(
        thumbnail_path=variants[0].thumbnail_path,
        thumbnail_key=variants[0].thumbnail_key,
        mode_used=mode,
        source_used=variants[0].source_used,
        width=payload.width,
        height=payload.height,
        variants=variants,
    )


@router.post("/thumbnail/set-primary", response_model=ThumbnailGenerateResponse)
def set_primary_thumbnail_endpoint(
    payload: ThumbnailSetPrimaryRequest,
) -> ThumbnailGenerateResponse:
    key = payload.thumbnail_key.strip().lstrip("/")
    allowed_prefix = f"{payload.project_id}/thumbnails/"
    if not key.startswith(allowed_prefix):
        raise HTTPException(status_code=400, detail="thumbnail_key must belong to project thumbnails")
    if not storage_client.exists(key):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    ext = Path(key).suffix.lower().lstrip(".")
    if ext not in _THUMBNAIL_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported thumbnail extension")

    content_type = "image/png" if ext == "png" else "image/jpeg"
    latest_key = project_key(payload.project_id, f"thumbnails/thumbnail_latest.{ext}")
    storage_client.write_bytes(
        latest_key,
        storage_client.read_bytes(key),
        content_type=content_type,
    )

    return ThumbnailGenerateResponse(
        thumbnail_path=storage_client.public_url(latest_key),
        thumbnail_key=latest_key,
        mode_used="set-primary",
        source_used=key,
        width=1280,
        height=720,
        variants=[
            ThumbnailVariantResponse(
                variant_id=1,
                thumbnail_key=latest_key,
                thumbnail_path=storage_client.public_url(latest_key),
                source_used=key,
                width=1280,
                height=720,
            )
        ],
    )


@router.post("/import", response_model=VideoImportResponse)
def import_video_endpoint(
    payload: VideoImportRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VideoImportResponse:
    response = requests.get(payload.url, stream=True, timeout=30)
    response.raise_for_status()
    chunks = []
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if chunk:
            chunks.append(chunk)
    key = project_key(payload.project_id, "video/imported.mp4")
    storage_client.write_bytes(key, b"".join(chunks), content_type="video/mp4")
    record_usage_event(
        session=session,
        user=current_user,
        action="video.import",
        reason="video url import",
        reference_id=payload.project_id,
        provider="remote_url",
        model="n/a",
        metadata={"url": payload.url},
    )
    return VideoImportResponse(video_path=storage_client.public_url(key))


@router.post("/auto-clip", response_model=FeatureStubResponse)
def auto_clip(project_id: str) -> FeatureStubResponse:
    scenes = read_scene_metadata(project_id)
    if not scenes:
        transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
        transcript_segments = read_json_artifact(transcript_path).get("segments", [])
        scenes = [
            {"id": segment.get("segment_id", idx + 1), "text": segment.get("text", "")}
            for idx, segment in enumerate(transcript_segments)
            if segment.get("text")
        ]
    if not scenes:
        raise HTTPException(
            status_code=400,
            detail="No scene or transcript data found. Generate script/transcript first.",
        )

    clips = []
    cursor = 0.0
    for idx, scene in enumerate(scenes or []):
        duration = max(8.0, min(18.0, len(scene.get("text", "").split()) * 0.5))
        clips.append(
            {
                "clip_id": idx + 1,
                "start": round(cursor, 2),
                "end": round(cursor + duration, 2),
                "reason": "High-information segment",
            }
        )
        cursor += duration
    artifact_path = PROJECTS_DIR / project_id / "video" / "clips.json"
    write_json_artifact(artifact_path, {"clips": clips})
    return FeatureStubResponse(
        status="complete",
        detail=f"Auto-clip suggestions saved to {artifact_path}",
    )


@router.post("/transcribe", response_model=FeatureStubResponse)
def transcribe(project_id: str) -> FeatureStubResponse:
    audio_candidates = [
        project_key(project_id, "audio/scene_1.wav"),
        project_key(project_id, "audio/scene_1.mp3"),
    ]
    for key in storage_client.list_keys(f"{project_id}/audio/"):
        if key.endswith((".wav", ".mp3", ".ogg", ".m4a")):
            audio_candidates.append(key)

    audio_key = next((key for key in audio_candidates if storage_client.exists(key)), None)
    segments = []

    if audio_key:
        try:
            import importlib

            whisper = importlib.import_module("whisper")
            model_name = "base"
            model = whisper.load_model(model_name)
            with tempfile.TemporaryDirectory(prefix="pro_creator_whisper_") as temp_dir:
                audio_path = Path(temp_dir) / Path(audio_key).name
                audio_path.write_bytes(storage_client.read_bytes(audio_key))
                result = model.transcribe(str(audio_path))
            for idx, seg in enumerate(result.get("segments", [])):
                segments.append(
                    {
                        "segment_id": idx + 1,
                        "start": round(seg["start"], 2),
                        "end": round(seg["end"], 2),
                        "text": seg["text"].strip(),
                    }
                )
        except Exception:
            segments = []

    if not segments:
        segments = fallback_segments(project_id)
    if not segments:
        raise HTTPException(
            status_code=400,
            detail="No transcript source found. Generate voice or provide script first.",
        )

    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    write_json_artifact(transcript_path, {"segments": segments})
    return FeatureStubResponse(
        status="complete",
        detail=f"Transcript saved to {transcript_path}",
    )


@router.post("/captions", response_model=FeatureStubResponse)
def captions(project_id: str) -> FeatureStubResponse:
    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    segments = read_json_artifact(transcript_path).get("segments", [])
    if not segments:
        raise HTTPException(
            status_code=400,
            detail="Transcript not found. Run transcription before caption generation.",
        )

    def to_timestamp(seconds: float) -> str:
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        return f"{int(hours):02d}:{int(mins):02d}:{secs:06.3f}".replace(".", ",")

    lines = []
    for idx, segment in enumerate(segments, start=1):
        lines.append(str(idx))
        lines.append(
            f"{to_timestamp(segment['start'])} --> {to_timestamp(segment['end'])}"
        )
        lines.append(segment["text"])
        lines.append("")

    captions_key = project_key(project_id, "video/captions.srt")
    storage_client.write_text(captions_key, "\n".join(lines))
    return FeatureStubResponse(
        status="complete",
        detail=f"Captions saved to {captions_key}",
    )


@router.post("/lipsync", response_model=FeatureStubResponse)
def lipsync(project_id: str) -> FeatureStubResponse:
    payload = generate_lipsync(project_id)
    if payload.get("source") == "disabled" or not payload.get("visemes"):
        raise HTTPException(
            status_code=400,
            detail="Lip sync data could not be generated. Ensure transcript/audio assets exist.",
        )
    lipsync_path = PROJECTS_DIR / project_id / "video" / "lipsync.json"
    return FeatureStubResponse(
        status="complete",
        detail=f"Lip sync data saved to {lipsync_path} ({payload.get('source')})",
    )


@router.post("/multitrack", response_model=FeatureStubResponse)
def multitrack(project_id: str) -> FeatureStubResponse:
    audio_keys = sorted(
        key for key in storage_client.list_keys(f"{project_id}/audio/") if key.endswith((".wav", ".mp3", ".ogg", ".m4a"))
    )
    if not audio_keys:
        raise HTTPException(
            status_code=400,
            detail="No audio tracks found. Generate voice before multitrack planning.",
        )

    tracks = []
    for idx, key in enumerate(audio_keys, start=1):
        tracks.append(
            {
                "track_id": idx,
                "type": "voice",
                "source": storage_client.public_url(key),
                "gain_db": -2,
            }
        )
    tracks.append(
        {
            "track_id": len(tracks) + 1,
            "type": "music",
            "source": "library://ambient-bed-01",
            "gain_db": -18,
            "duck_under_voice_db": -10,
        }
    )

    multitrack_path = PROJECTS_DIR / project_id / "audio" / "multitrack.json"
    write_json_artifact(multitrack_path, {"tracks": tracks})
    return FeatureStubResponse(
        status="complete",
        detail=f"Multitrack plan saved to {multitrack_path}",
    )


@router.post("/scene-detect", response_model=FeatureStubResponse)
def scene_detect(project_id: str) -> FeatureStubResponse:
    scenes = read_scene_metadata(project_id)
    if not scenes and not storage_client.exists(project_key(project_id, "video/imported.mp4")) and not storage_client.exists(project_key(project_id, "video/final.mp4")):
        raise HTTPException(
            status_code=400,
            detail="No source video or scene data found for scene detection.",
        )

    if not scenes:
        transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
        segments = read_json_artifact(transcript_path).get("segments", [])
        scenes = [
            {
                "id": idx + 1,
                "start": segment.get("start", idx * 10.0),
                "end": segment.get("end", (idx + 1) * 10.0),
            }
            for idx, segment in enumerate(segments)
        ]
    if not scenes:
        scenes = [{"id": 1, "start": 0.0, "end": 12.0}]
    else:
        scenes = [
            {
                "scene_id": scene.get("id", idx + 1),
                "start": round(idx * 12.0, 2),
                "end": round((idx + 1) * 12.0, 2),
                "confidence": 0.8,
            }
            for idx, scene in enumerate(scenes)
        ]
    scene_path = PROJECTS_DIR / project_id / "video" / "scene_detection.json"
    write_json_artifact(scene_path, {"scenes": scenes})
    return FeatureStubResponse(
        status="complete",
        detail=f"Scene detection saved to {scene_path}",
    )


@router.get("/artifacts/{project_id}/transcript")
def get_transcript(project_id: str) -> dict:
    path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    return read_json_artifact(path)


@router.get("/artifacts/{project_id}/clips")
def get_clips(project_id: str) -> dict:
    path = PROJECTS_DIR / project_id / "video" / "clips.json"
    return read_json_artifact(path)


@router.get("/artifacts/{project_id}/scene-detection")
def get_scene_detection(project_id: str) -> dict:
    path = PROJECTS_DIR / project_id / "video" / "scene_detection.json"
    return read_json_artifact(path)


@router.get("/artifacts/{project_id}/multitrack")
def get_multitrack(project_id: str) -> dict:
    path = PROJECTS_DIR / project_id / "audio" / "multitrack.json"
    return read_json_artifact(path)


@router.get("/artifacts/{project_id}/lipsync")
def get_lipsync(project_id: str) -> dict:
    path = PROJECTS_DIR / project_id / "video" / "lipsync.json"
    return read_json_artifact(path)


@router.get("/artifacts/{project_id}/captions")
def get_captions(project_id: str) -> dict:
    key = project_key(project_id, "video/captions.srt")
    if not storage_client.exists(key):
        return {"captions": ""}
    return {"captions": storage_client.read_text(key)}


@router.post("/export", response_model=ExportPresetResponse)
def export_preset(
    payload: ExportPresetRequest,
    session: Session | None = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> ExportPresetResponse:
    presets = {
        "youtube": (1920, 1080),
        "tiktok": (1080, 1920),
        "instagram": (1080, 1350),
        "facebook": (1280, 720),
        "x": (1920, 1080),
    }
    width, height = presets.get(payload.preset, (1280, 720))
    source_key = project_key(payload.project_id, "video/final.mp4")
    if not storage_client.exists(source_key):
        source_key = project_key(payload.project_id, "video/imported.mp4")
    if not storage_client.exists(source_key):
        raise HTTPException(
            status_code=400,
            detail="No source video found. Render or import a video before exporting.",
        )

    with tempfile.TemporaryDirectory(prefix="pro_creator_export_") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = temp_path / "source.mp4"
        target_path = temp_path / f"{payload.preset}.mp4"

        if storage_client.exists(source_key):
            source_path.write_bytes(storage_client.read_bytes(source_key))

        if source_path.exists():
            # Use a bounded ffmpeg subprocess instead of ffmpeg-python to avoid
            # unbounded hangs during export.
            ffmpeg_path = shutil.which("ffmpeg")
            if ffmpeg_path:
                try:
                    subprocess.run(
                        [
                            ffmpeg_path,
                            "-y",
                            "-i",
                            str(source_path),
                            "-vf",
                            f"scale={width}:{height}",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-crf",
                            "28",
                            "-c:a",
                            "aac",
                            "-movflags",
                            "+faststart",
                            str(target_path),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                    )
                except Exception:
                    target_path.write_bytes(source_path.read_bytes())
            else:
                target_path.write_bytes(source_path.read_bytes())
        export_key = project_key(payload.project_id, f"video/exports/{payload.preset}.mp4")
        storage_client.write_bytes(
            export_key,
            target_path.read_bytes(),
            content_type="video/mp4",
        )
    if isinstance(session, Session) and isinstance(current_user, User):
        consume_credits(
            session=session,
            user=current_user,
            amount=CREDITS_COST_VIDEO_EXPORT,
            reason="video export",
            action="video.export",
            reference_id=payload.project_id,
            provider="local",
            model=payload.preset,
        )

    return ExportPresetResponse(export_path=storage_client.public_url(export_key))


@router.post("/export/batch", response_model=ExportBatchResponse)
def export_batch(
    payload: ExportBatchRequest,
    session: Session | None = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> ExportBatchResponse:
    exports = []
    for preset in payload.presets:
        result = export_preset(
            ExportPresetRequest(project_id=payload.project_id, preset=preset),
            session=session,
            current_user=current_user,
        )
        exports.append(result.export_path)
    return ExportBatchResponse(exports=exports)


@router.get("/export/status/{project_id}", response_model=ExportStatusResponse)
def export_status(
    project_id: str,
    presets: list[str] | None = Query(default=None),
) -> ExportStatusResponse:
    default_presets = ["youtube", "tiktok", "instagram", "facebook", "x"]
    requested = presets or default_presets
    entries: list[ExportStatusEntry] = []

    for preset in requested:
        key = project_key(project_id, f"video/exports/{preset}.mp4")
        if storage_client.exists(key):
            if storage_client.backend == "local":
                path = PROJECTS_DIR / key
                stat = path.stat()
                size_bytes = stat.st_size
                updated_at = datetime.fromtimestamp(stat.st_mtime)
            else:
                size_bytes = None
                updated_at = None
            entries.append(
                ExportStatusEntry(
                    preset=preset,
                    status="complete",
                    path=storage_client.public_url(key),
                    size_bytes=size_bytes,
                    updated_at=updated_at,
                )
            )
        else:
            entries.append(ExportStatusEntry(preset=preset, status="queued"))

    return ExportStatusResponse(project_id=project_id, exports=entries)


@router.post("/edit-by-text", response_model=EditByTextResponse)
def edit_by_text(payload: EditByTextRequest) -> EditByTextResponse:
    transcript_path = PROJECTS_DIR / payload.project_id / "video" / "transcript.json"
    transcript = read_json_artifact(transcript_path)
    segments = transcript.get("segments", [])

    def overlaps(segment: dict, ranges: list[list[float]]) -> bool:
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        for r in ranges:
            if len(r) != 2:
                continue
            if end >= r[0] and start <= r[1]:
                return True
        return False

    filtered = [seg for seg in segments if not overlaps(seg, payload.remove_ranges)]
    write_json_artifact(transcript_path, {"segments": filtered})
    return EditByTextResponse(segments_remaining=len(filtered))


@router.post("/magic-cut", response_model=FeatureStubResponse)
def magic_cut(project_id: str) -> FeatureStubResponse:
    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    transcript = read_json_artifact(transcript_path)
    segments = transcript.get("segments", [])

    if not segments:
        segments = fallback_segments(project_id)
        if segments:
            write_json_artifact(transcript_path, {"segments": segments})

    kept_segments = []
    removed_segments = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        duration = max(0.0, end - start)
        word_count = len(text.split())
        keep = word_count >= 3 and duration >= 0.35
        if keep:
            kept_segments.append(seg)
        else:
            removed_segments.append(seg)

    keep_ranges = [
        [round(float(seg.get("start", 0.0)), 2), round(float(seg.get("end", 0.0)), 2)]
        for seg in kept_segments
    ]
    total_kept = sum(
        max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
        for seg in kept_segments
    )
    total_original = sum(
        max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
        for seg in segments
    )

    artifact_path = PROJECTS_DIR / project_id / "video" / "magic_cut.json"
    write_json_artifact(
        artifact_path,
        {
            "project_id": project_id,
            "original_segments": len(segments),
            "kept_segments": len(kept_segments),
            "removed_segments": removed_segments,
            "keep_ranges": keep_ranges,
            "duration_seconds_original": round(total_original, 2),
            "duration_seconds_kept": round(total_kept, 2),
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Magic cut analysis saved to {artifact_path}",
    )


@router.post("/screen-record", response_model=FeatureStubResponse)
def screen_record(project_id: str) -> FeatureStubResponse:
    scenes = read_scene_metadata(project_id)
    timeline = []
    cursor = 0.0
    for idx, scene in enumerate(scenes or []):
        text = str(scene.get("text", "")).strip()
        duration = max(6.0, min(20.0, len(text.split()) * 0.45 if text else 8.0))
        timeline.append(
            {
                "scene_id": scene.get("id", idx + 1),
                "start": round(cursor, 2),
                "end": round(cursor + duration, 2),
                "layout": "screen+webcam",
                "webcam_position": "bottom-right",
                "notes": text[:160] if text else "Narration-driven scene",
            }
        )
        cursor += duration

    if not timeline:
        timeline = [
            {
                "scene_id": 1,
                "start": 0.0,
                "end": 10.0,
                "layout": "screen+webcam",
                "webcam_position": "bottom-right",
                "notes": "Default recording segment",
            }
        ]

    artifact_path = PROJECTS_DIR / project_id / "video" / "screen_record_plan.json"
    write_json_artifact(
        artifact_path,
        {
            "project_id": project_id,
            "resolution": "1920x1080",
            "fps": 30,
            "timeline": timeline,
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Screen recording plan saved to {artifact_path}",
    )


@router.post("/templates", response_model=FeatureStubResponse)
def templates(project_id: str) -> FeatureStubResponse:
    script_key = project_key(project_id, "script.txt")
    script = storage_client.read_text(script_key).lower()
    if any(token in script for token in ["tutorial", "how to", "walkthrough"]):
        selected = "tutorial"
    elif any(token in script for token in ["product", "sale", "offer", "cta"]):
        selected = "promo"
    elif any(token in script for token in ["podcast", "interview", "talk"]):
        selected = "talking-head"
    else:
        selected = "cinematic"

    template_catalog = [
        {"id": "cinematic", "aspect_ratio": "16:9", "transition": "crossfade"},
        {"id": "tutorial", "aspect_ratio": "16:9", "transition": "cut"},
        {"id": "promo", "aspect_ratio": "9:16", "transition": "zoom"},
        {"id": "talking-head", "aspect_ratio": "1:1", "transition": "slide"},
    ]
    artifact_path = PROJECTS_DIR / project_id / "video" / "template_plan.json"
    write_json_artifact(
        artifact_path,
        {
            "project_id": project_id,
            "selected_template": selected,
            "available_templates": template_catalog,
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Template selection saved to {artifact_path}",
    )


@router.post("/export-presets", response_model=FeatureStubResponse)
def export_presets(project_id: str) -> FeatureStubResponse:
    presets = [
        {"preset": "youtube", "resolution": "1920x1080", "fps": 30, "audio": "aac"},
        {"preset": "tiktok", "resolution": "1080x1920", "fps": 30, "audio": "aac"},
        {"preset": "instagram", "resolution": "1080x1350", "fps": 30, "audio": "aac"},
        {"preset": "facebook", "resolution": "1280x720", "fps": 30, "audio": "aac"},
        {"preset": "x", "resolution": "1920x1080", "fps": 30, "audio": "aac"},
    ]
    template_path = PROJECTS_DIR / project_id / "video" / "template_plan.json"
    template_plan = read_json_artifact(template_path)
    selected_template = str(template_plan.get("selected_template", "cinematic"))
    recommended = "youtube"
    if selected_template == "promo":
        recommended = "tiktok"
    elif selected_template == "talking-head":
        recommended = "instagram"

    artifact_path = PROJECTS_DIR / project_id / "video" / "export_presets.json"
    write_json_artifact(
        artifact_path,
        {
            "project_id": project_id,
            "recommended": recommended,
            "presets": presets,
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Export presets saved to {artifact_path}",
    )
