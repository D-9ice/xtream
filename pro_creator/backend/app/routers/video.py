from datetime import datetime
import io
import json
import ipaddress
import re
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Query, Depends, File, HTTPException, UploadFile
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
    PROJECTS_DIR,
    VIDEO_IMPORT_CONNECT_TIMEOUT_SECONDS,
    VIDEO_IMPORT_MAX_BYTES,
    VIDEO_IMPORT_MAX_REDIRECTS,
    VIDEO_IMPORT_READ_TIMEOUT_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_STT_MODEL,
    XAI_VIDEO_MODEL,
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
_ALLOWED_REMOTE_VIDEO_TYPES = {"application/octet-stream", "binary/octet-stream"}


def _validate_public_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Video import URL must use http or https.")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Credentials in video import URLs are not allowed.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise HTTPException(status_code=400, detail="Local/private video import URLs are blocked.")
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="Video import host could not be resolved.") from exc
    if not addresses:
        raise HTTPException(status_code=400, detail="Video import host could not be resolved.")
    for entry in addresses:
        raw_address = str(entry[4][0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Video import resolved to an invalid address.") from exc
        if not address.is_global:
            raise HTTPException(status_code=400, detail="Local/private video import URLs are blocked.")


def _open_remote_video(url: str) -> tuple[requests.Response, str]:
    current_url = url
    for _ in range(VIDEO_IMPORT_MAX_REDIRECTS + 1):
        _validate_public_remote_url(current_url)
        response = requests.get(
            current_url,
            stream=True,
            timeout=(VIDEO_IMPORT_CONNECT_TIMEOUT_SECONDS, VIDEO_IMPORT_READ_TIMEOUT_SECONDS),
            allow_redirects=False,
            headers={"Accept": "video/*,application/octet-stream;q=0.8"},
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise HTTPException(status_code=400, detail="Video import redirect did not include a destination.")
            current_url = urljoin(current_url, location)
            continue
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            response.close()
            raise HTTPException(status_code=400, detail="Remote video could not be downloaded.") from exc
        return response, current_url
    raise HTTPException(status_code=400, detail="Video import exceeded the allowed redirect limit.")


def _validate_downloaded_video(path: Path) -> None:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise HTTPException(status_code=503, detail="ffprobe is required to validate imported video.")
    try:
        probe = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=400, detail="Imported media could not be validated.") from exc
    if probe.returncode != 0 or "video" not in probe.stdout.lower():
        raise HTTPException(status_code=400, detail="Remote content is not a valid video file.")


def _redact_remote_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _source_video_key(project_id: str) -> str:
    candidates = [
        project_key(project_id, "video/edited.mp4"),
        project_key(project_id, "video/final.mp4"),
        project_key(project_id, "video/imported.mp4"),
    ]
    key = next((item for item in candidates if storage_client.exists(item)), None)
    if not key:
        raise HTTPException(status_code=400, detail="No source video found for this operation.")
    return key


def _ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise HTTPException(status_code=503, detail="ffmpeg is required for media processing.")
    return path


def _ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise HTTPException(status_code=503, detail="ffprobe is required for media validation.")
    return path


def _probe_media(path: Path) -> dict:
    try:
        result = subprocess.run(
            [
                _ffprobe_path(),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail="Media validation failed.") from exc
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail="Media file is unreadable or invalid.")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Media probe returned invalid metadata.") from exc
    streams = payload.get("streams") or []
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video_stream:
        raise HTTPException(status_code=400, detail="Media file does not contain a video stream.")
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": max(0.0, duration),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "has_audio": any(item.get("codec_type") == "audio" for item in streams),
    }


def _segments_from_xai_words(words: list[dict], fallback_text: str, duration: float) -> list[dict]:
    if not words:
        text = fallback_text.strip()
        return [
            {
                "segment_id": 1,
                "start": 0.0,
                "end": round(max(0.0, duration), 2),
                "text": text,
            }
        ] if text else []

    segments: list[dict] = []
    bucket: list[str] = []
    bucket_start: float | None = None
    bucket_end = 0.0
    for word in words:
        text = str(word.get("text") or word.get("word") or "").strip()
        if not text:
            continue
        try:
            start = float(word.get("start") or 0.0)
            end = float(word.get("end") or start)
        except (TypeError, ValueError):
            continue
        if bucket_start is None:
            bucket_start = start
        bucket.append(text)
        bucket_end = max(bucket_end, end)
        elapsed = bucket_end - bucket_start
        sentence_end = text.endswith((".", "!", "?"))
        if elapsed >= 8.0 or sentence_end:
            segments.append(
                {
                    "segment_id": len(segments) + 1,
                    "start": round(bucket_start, 2),
                    "end": round(bucket_end, 2),
                    "text": " ".join(bucket).strip(),
                }
            )
            bucket = []
            bucket_start = None
            bucket_end = 0.0
    if bucket and bucket_start is not None:
        segments.append(
            {
                "segment_id": len(segments) + 1,
                "start": round(bucket_start, 2),
                "end": round(bucket_end, 2),
                "text": " ".join(bucket).strip(),
            }
        )
    return segments


def _transcribe_with_xai(audio_path: Path) -> tuple[list[dict], dict]:
    if not XAI_API_KEY:
        raise HTTPException(status_code=503, detail="xAI speech transcription is not configured.")
    suffix = audio_path.suffix.lower()
    content_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
    }
    try:
        with audio_path.open("rb") as handle:
            response = requests.post(
                f"{XAI_BASE_URL}/stt",
                headers={"Authorization": f"Bearer {XAI_API_KEY}"},
                data=[("model", XAI_STT_MODEL), ("format", "true")],
                files={
                    "file": (
                        audio_path.name,
                        handle,
                        content_types.get(suffix, "application/octet-stream"),
                    )
                },
                timeout=(10, 300),
            )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("xAI speech transcription failed: %s", exc)
        raise HTTPException(status_code=502, detail="xAI speech transcription failed.") from exc

    try:
        duration = float(payload.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    segments = _segments_from_xai_words(
        payload.get("words") or [],
        str(payload.get("text") or ""),
        duration,
    )
    if not segments:
        raise HTTPException(status_code=502, detail="xAI speech transcription returned no transcript.")
    return segments, {
        "provider": "xai",
        "model": XAI_STT_MODEL,
        "language": payload.get("language"),
        "duration": duration,
    }


def _materialize_video(project_id: str, temp_path: Path) -> tuple[str, Path, dict]:
    key = _source_video_key(project_id)
    source = temp_path / "source.mp4"
    source.write_bytes(storage_client.read_bytes(key))
    return key, source, _probe_media(source)


async def _save_upload_bounded(upload: UploadFile, target: Path) -> int:
    total = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > VIDEO_IMPORT_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Recording exceeds the configured media size limit.",
                    )
                handle.write(chunk)
    finally:
        await upload.close()
    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded recording is empty.")
    return total


def _run_ffmpeg(arguments: list[str], *, timeout: int = 600) -> None:
    try:
        result = subprocess.run(
            [_ffmpeg_path(), "-y", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail="Media processing failed or timed out.") from exc
    if result.returncode != 0:
        logger.error("ffmpeg failed: %s", (result.stderr or "")[-2000:])
        raise HTTPException(status_code=500, detail="Media processing failed.")


def _normalize_ranges(ranges: list[list[float]], duration: float) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for item in ranges:
        if len(item) != 2:
            continue
        try:
            start = max(0.0, float(item[0]))
            end = min(duration, float(item[1]))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        normalized.append((start, end))
    normalized.sort()
    merged: list[tuple[float, float]] = []
    for start, end in normalized:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _complement_ranges(duration: float, remove_ranges: list[list[float]]) -> list[tuple[float, float]]:
    removed = _normalize_ranges(remove_ranges, duration)
    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in removed:
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        kept.append((cursor, duration))
    return [(start, end) for start, end in kept if end - start >= 0.05]


def _render_ranges_to_video(source: Path, target: Path, ranges: list[tuple[float, float]]) -> dict:
    source_meta = _probe_media(source)
    if not ranges:
        raise HTTPException(status_code=400, detail="No video duration remains after the requested edit.")
    segment_paths: list[Path] = []
    for index, (start, end) in enumerate(ranges, start=1):
        segment = target.parent / f"segment_{index:03d}.mp4"
        args = [
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
        if source_meta["has_audio"]:
            args.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            args.append("-an")
        args.extend(["-movflags", "+faststart", str(segment)])
        _run_ffmpeg(args)
        segment_paths.append(segment)

    concat_file = target.parent / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{segment.as_posix()}'" for segment in segment_paths),
        encoding="utf-8",
    )
    _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    return _probe_media(target)


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
    preferred_provider = "xai" if XAI_API_KEY.strip() else "local"
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
        result = render_video(payload.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    consume_credits(
        session=session,
        user=current_user,
        amount=CREDITS_COST_VIDEO_RENDER,
        reason="video render",
        action="video.render",
        reference_id=payload.project_id,
        provider="xai",
        model=XAI_VIDEO_MODEL,
    )
    logger.info(
        "Rendered video for project %s provider=%s model=%s",
        payload.project_id,
        "grok_imagine",
        XAI_VIDEO_MODEL,
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
    response, final_url = _open_remote_video(payload.url)
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type and not (content_type.startswith("video/") or content_type in _ALLOWED_REMOTE_VIDEO_TYPES):
        response.close()
        raise HTTPException(status_code=415, detail="Remote URL did not return video content.")

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > VIDEO_IMPORT_MAX_BYTES:
                response.close()
                raise HTTPException(status_code=413, detail="Remote video exceeds the configured import size limit.")
        except ValueError:
            pass

    temp_path: Path | None = None
    try:
        total_bytes = 0
        with tempfile.NamedTemporaryFile(prefix="procreator-import-", suffix=".video", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > VIDEO_IMPORT_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Remote video exceeds the configured import size limit.")
                temp_file.write(chunk)
        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Remote video download was empty.")
        _validate_downloaded_video(temp_path)
        key = project_key(payload.project_id, "video/imported.mp4")
        storage_client.write_file(key, temp_path, content_type="video/mp4")
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail="Remote video download failed.") from exc
    finally:
        response.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    record_usage_event(
        session=session,
        user=current_user,
        action="video.import",
        reason="video url import",
        reference_id=payload.project_id,
        provider="remote_url",
        model="n/a",
        metadata={"url": _redact_remote_url(final_url)},
    )
    return VideoImportResponse(video_path=storage_client.public_url(key))


@router.post("/auto-clip", response_model=FeatureStubResponse)
def auto_clip(project_id: str) -> FeatureStubResponse:
    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    transcript_segments = read_json_artifact(transcript_path).get("segments", [])
    with tempfile.TemporaryDirectory(prefix="pro_creator_autoclip_") as temp_dir:
        temp_path = Path(temp_dir)
        _, source_path, source_meta = _materialize_video(project_id, temp_path)
        duration = source_meta["duration"]
        candidates: list[tuple[float, float, str]] = []
        for segment in transcript_segments:
            try:
                start = float(segment.get("start", 0.0))
                end = float(segment.get("end", start))
            except (TypeError, ValueError):
                continue
            text = str(segment.get("text", "")).strip()
            if text and end > start:
                candidates.append((start, end, text))
        if not candidates:
            scenes = read_scene_metadata(project_id)
            cursor = 0.0
            for scene in scenes or []:
                text = str(scene.get("text", "")).strip()
                clip_duration = max(8.0, min(18.0, len(text.split()) * 0.5 if text else 8.0))
                candidates.append((cursor, min(duration, cursor + clip_duration), text))
                cursor += clip_duration
                if cursor >= duration:
                    break
        if not candidates:
            raise HTTPException(status_code=400, detail="No transcript or scene data found for auto-clipping.")

        clips = []
        for idx, (start, end, text) in enumerate(candidates[:12], start=1):
            normalized = _normalize_ranges([[start, end]], duration)
            if not normalized:
                continue
            target = temp_path / f"clip_{idx:03d}.mp4"
            meta = _render_ranges_to_video(source_path, target, normalized)
            key = project_key(project_id, f"video/clips/clip_{idx:03d}.mp4")
            storage_client.write_file(key, target, content_type="video/mp4")
            clips.append(
                {
                    "clip_id": idx,
                    "start": round(normalized[0][0], 2),
                    "end": round(normalized[0][1], 2),
                    "reason": "Transcript/scene segment",
                    "text": text[:200],
                    "video_path": storage_client.public_url(key),
                    "duration": round(meta["duration"], 2),
                }
            )
    if not clips:
        raise HTTPException(status_code=400, detail="No usable clip ranges were found.")
    artifact_path = PROJECTS_DIR / project_id / "video" / "clips.json"
    write_json_artifact(artifact_path, {"clips": clips})
    return FeatureStubResponse(
        status="complete",
        detail=f"{len(clips)} media clip(s) created.",
    )

@router.post("/transcribe", response_model=FeatureStubResponse)
def transcribe(project_id: str) -> FeatureStubResponse:
    audio_candidates = [
        project_key(project_id, "audio/scene_1.wav"),
        project_key(project_id, "audio/scene_1.mp3"),
        project_key(project_id, "audio/scene_1.m4a"),
        project_key(project_id, "audio/scene_1.ogg"),
    ]
    for key in storage_client.list_keys(f"{project_id}/audio/"):
        if key.endswith((".wav", ".mp3", ".ogg", ".m4a", ".webm")):
            audio_candidates.append(key)
    audio_key = next((key for key in audio_candidates if storage_client.exists(key)), None)
    if not audio_key:
        raise HTTPException(
            status_code=400,
            detail="No audio source found. Generate or import audio before transcription.",
        )

    with tempfile.TemporaryDirectory(prefix="pro_creator_xai_stt_") as temp_dir:
        audio_path = Path(temp_dir) / (Path(audio_key).name or "audio.m4a")
        audio_path.write_bytes(storage_client.read_bytes(audio_key))
        if not audio_path.stat().st_size:
            raise HTTPException(status_code=400, detail="Audio source is empty.")
        segments, metadata = _transcribe_with_xai(audio_path)

    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    write_json_artifact(
        transcript_path,
        {
            "segments": segments,
            "source": "xai_stt",
            "provider": metadata["provider"],
            "model": metadata["model"],
            "language": metadata["language"],
            "duration": metadata["duration"],
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Speech transcript created with {metadata['model']} ({len(segments)} segment(s)).",
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
        key for key in storage_client.list_keys(f"{project_id}/audio/")
        if key.endswith((".wav", ".mp3", ".ogg", ".m4a"))
    )
    voice_keys = [key for key in audio_keys if not any(token in key.lower() for token in ("music", "bed", "ambient"))]
    music_keys = [key for key in audio_keys if key not in voice_keys]
    if not voice_keys:
        raise HTTPException(status_code=400, detail="No voice audio tracks found.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_multitrack_") as temp_dir:
        temp_path = Path(temp_dir)
        voice_files: list[Path] = []
        for idx, key in enumerate(voice_keys, start=1):
            path = temp_path / f"voice_{idx:03d}{Path(key).suffix or '.m4a'}"
            path.write_bytes(storage_client.read_bytes(key))
            voice_files.append(path)

        concat_file = temp_path / "voice_concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in voice_files),
            encoding="utf-8",
        )
        narration = temp_path / "narration.m4a"
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-vn", "-c:a", "aac", "-b:a", "192k", str(narration),
        ])

        output = temp_path / "multitrack_mix.m4a"
        if music_keys:
            music = temp_path / f"music{Path(music_keys[0]).suffix or '.m4a'}"
            music.write_bytes(storage_client.read_bytes(music_keys[0]))
            _run_ffmpeg([
                "-i", str(narration),
                "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                "[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(output),
            ])
        else:
            shutil.copyfile(narration, output)

        output_key = project_key(project_id, "audio/multitrack_mix.m4a")
        storage_client.write_file(output_key, output, content_type="audio/mp4")

    tracks = [
        {
            "track_id": idx,
            "type": "voice",
            "source": storage_client.public_url(key),
            "gain_db": -2,
        }
        for idx, key in enumerate(voice_keys, start=1)
    ]
    if music_keys:
        tracks.append(
            {
                "track_id": len(tracks) + 1,
                "type": "music",
                "source": storage_client.public_url(music_keys[0]),
                "gain_db": -18,
            }
        )
    multitrack_path = PROJECTS_DIR / project_id / "audio" / "multitrack.json"
    write_json_artifact(
        multitrack_path,
        {"tracks": tracks, "mixed_output": storage_client.public_url(output_key)},
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Mixed audio master created at {storage_client.public_url(output_key)}",
    )

@router.post("/scene-detect", response_model=FeatureStubResponse)
def scene_detect(project_id: str) -> FeatureStubResponse:
    with tempfile.TemporaryDirectory(prefix="pro_creator_scene_detect_") as temp_dir:
        temp_path = Path(temp_dir)
        _, source_path, meta = _materialize_video(project_id, temp_path)
        try:
            result = subprocess.run(
                [
                    _ffmpeg_path(),
                    "-i",
                    str(source_path),
                    "-filter:v",
                    "select='gt(scene,0.35)',metadata=print",
                    "-an",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(status_code=500, detail="Scene detection failed or timed out.") from exc
        if result.returncode != 0:
            logger.error("scene detection ffmpeg failed: %s", (result.stderr or "")[-2000:])
            raise HTTPException(status_code=500, detail="Scene detection failed.")

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        timestamps = [0.0]
        scores: dict[float, float] = {}
        current_time: float | None = None
        for line in output.splitlines():
            time_match = re.search(r"pts_time:([0-9.]+)", line)
            if time_match:
                current_time = float(time_match.group(1))
                if 0.0 < current_time < meta["duration"]:
                    timestamps.append(current_time)
            score_match = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
            if score_match and current_time is not None:
                scores[round(current_time, 3)] = float(score_match.group(1))
        timestamps.append(meta["duration"])
        timestamps = sorted(set(round(value, 3) for value in timestamps if value >= 0.0))
        scenes = []
        for idx in range(len(timestamps) - 1):
            start, end = timestamps[idx], timestamps[idx + 1]
            if end - start < 0.05:
                continue
            scenes.append(
                {
                    "scene_id": idx + 1,
                    "start": start,
                    "end": end,
                    "confidence": scores.get(round(start, 3)),
                    "method": "ffmpeg_scene_change",
                    "threshold": 0.35,
                }
            )
    scene_path = PROJECTS_DIR / project_id / "video" / "scene_detection.json"
    write_json_artifact(scene_path, {"scenes": scenes})
    return FeatureStubResponse(
        status="complete",
        detail=f"{len(scenes)} scene interval(s) detected from source media.",
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
        # Internal scheduler alias; not exposed as a new UI preset.
        "social-vertical": (1080, 1920),
    }
    if payload.preset not in presets:
        raise HTTPException(status_code=400, detail="Unsupported export preset.")
    width, height = presets[payload.preset]

    with tempfile.TemporaryDirectory(prefix="pro_creator_export_") as temp_dir:
        temp_path = Path(temp_dir)
        _, source_path, _ = _materialize_video(payload.project_id, temp_path)
        target_path = temp_path / f"{payload.preset}.mp4"
        filter_graph = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
        _run_ffmpeg(
            [
                "-i",
                str(source_path),
                "-vf",
                filter_graph,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(target_path),
            ]
        )
        meta = _probe_media(target_path)
        if meta["width"] != width or meta["height"] != height or meta["duration"] <= 0:
            raise HTTPException(status_code=500, detail="Export validation failed.")
        export_key = project_key(payload.project_id, f"video/exports/{payload.preset}.mp4")
        storage_client.write_file(export_key, target_path, content_type="video/mp4")
        metadata_key = project_key(payload.project_id, f"video/exports/{payload.preset}.json")
        storage_client.write_text(
            metadata_key,
            json.dumps(
                {
                    "preset": payload.preset,
                    "width": meta["width"],
                    "height": meta["height"],
                    "duration": meta["duration"],
                    "validated": True,
                },
                sort_keys=True,
            ),
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
        metadata_key = project_key(project_id, f"video/exports/{preset}.json")
        if storage_client.exists(key):
            verified = False
            if storage_client.exists(metadata_key):
                try:
                    verified = bool(json.loads(storage_client.read_text(metadata_key)).get("validated"))
                except (json.JSONDecodeError, AttributeError):
                    verified = False
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
                    status="complete" if verified else "unverified",
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
    if not segments:
        raise HTTPException(status_code=400, detail="Transcript not found. Run transcription first.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_text_edit_") as temp_dir:
        temp_path = Path(temp_dir)
        _, source_path, meta = _materialize_video(payload.project_id, temp_path)
        keep_ranges = _complement_ranges(meta["duration"], payload.remove_ranges)
        target = temp_path / "edited.mp4"
        output_meta = _render_ranges_to_video(source_path, target, keep_ranges)
        output_key = project_key(payload.project_id, "video/edited.mp4")
        storage_client.write_file(output_key, target, content_type="video/mp4")

    original_path = PROJECTS_DIR / payload.project_id / "video" / "transcript_original.json"
    if not original_path.exists():
        write_json_artifact(original_path, transcript)

    normalized_removed = _normalize_ranges(payload.remove_ranges, meta["duration"])

    def overlaps(segment: dict) -> bool:
        try:
            start = float(segment.get("start", 0))
            end = float(segment.get("end", 0))
        except (TypeError, ValueError):
            return False
        return any(end > cut_start and start < cut_end for cut_start, cut_end in normalized_removed)

    filtered = [seg for seg in segments if not overlaps(seg)]
    write_json_artifact(transcript_path, {"segments": filtered})
    write_json_artifact(
        PROJECTS_DIR / payload.project_id / "video" / "edit_by_text.json",
        {
            "remove_ranges": [[start, end] for start, end in normalized_removed],
            "keep_ranges": [[start, end] for start, end in keep_ranges],
            "video_path": storage_client.public_url(output_key),
            "duration": output_meta["duration"],
        },
    )
    return EditByTextResponse(
        segments_remaining=len(filtered),
        video_path=storage_client.public_url(output_key),
    )

@router.post("/magic-cut", response_model=FeatureStubResponse)
def magic_cut(project_id: str) -> FeatureStubResponse:
    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    transcript = read_json_artifact(transcript_path)
    segments = transcript.get("segments", [])
    if not segments:
        segments = fallback_segments(project_id)
    if not segments:
        raise HTTPException(status_code=400, detail="Transcript data is required for Magic Cut.")

    kept_segments = []
    removed_segments = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        duration = max(0.0, end - start)
        keep = len(text.split()) >= 3 and duration >= 0.35
        (kept_segments if keep else removed_segments).append(seg)

    with tempfile.TemporaryDirectory(prefix="pro_creator_magic_cut_") as temp_dir:
        temp_path = Path(temp_dir)
        _, source_path, meta = _materialize_video(project_id, temp_path)
        keep_ranges = _normalize_ranges(
            [[float(seg.get("start", 0.0)), float(seg.get("end", 0.0))] for seg in kept_segments],
            meta["duration"],
        )
        target = temp_path / "magic_cut.mp4"
        output_meta = _render_ranges_to_video(source_path, target, keep_ranges)
        output_key = project_key(project_id, "video/magic_cut.mp4")
        storage_client.write_file(output_key, target, content_type="video/mp4")

    artifact_path = PROJECTS_DIR / project_id / "video" / "magic_cut.json"
    write_json_artifact(
        artifact_path,
        {
            "project_id": project_id,
            "original_segments": len(segments),
            "kept_segments": len(kept_segments),
            "removed_segments": removed_segments,
            "keep_ranges": [[start, end] for start, end in keep_ranges],
            "output_path": storage_client.public_url(output_key),
            "duration_seconds_kept": round(output_meta["duration"], 2),
        },
    )
    return FeatureStubResponse(
        status="complete",
        detail=f"Magic Cut media created at {storage_client.public_url(output_key)}",
    )

@router.post("/screen-record", response_model=FeatureStubResponse)
async def screen_record(
    project_id: str,
    screen: UploadFile | None = File(default=None),
    webcam: UploadFile | None = File(default=None),
) -> FeatureStubResponse:
    if screen is None:
        raise HTTPException(
            status_code=400,
            detail="A captured screen recording file is required.",
        )

    with tempfile.TemporaryDirectory(prefix="pro_creator_screen_record_") as temp_dir:
        temp_path = Path(temp_dir)
        screen_ext = Path(screen.filename or "screen.webm").suffix or ".webm"
        screen_path = temp_path / f"screen{screen_ext}"
        await _save_upload_bounded(screen, screen_path)
        screen_meta = _probe_media(screen_path)

        webcam_path: Path | None = None
        webcam_meta: dict | None = None
        if webcam is not None:
            webcam_ext = Path(webcam.filename or "webcam.webm").suffix or ".webm"
            webcam_path = temp_path / f"webcam{webcam_ext}"
            await _save_upload_bounded(webcam, webcam_path)
            webcam_meta = _probe_media(webcam_path)

        output = temp_path / "screen_record.mp4"
        if webcam_path is not None:
            audio_input = "0:a?" if screen_meta["has_audio"] else ("1:a?" if webcam_meta and webcam_meta["has_audio"] else None)
            args = [
                "-i", str(screen_path),
                "-i", str(webcam_path),
                "-filter_complex",
                "[1:v][0:v]scale2ref=w=main_w*0.24:h=ow/mdar[cam][base];"
                "[base][cam]overlay=W-w-24:H-h-24:shortest=1[v]",
                "-map", "[v]",
            ]
            if audio_input:
                args.extend(["-map", audio_input])
            args.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
            ])
            if audio_input:
                args.extend(["-c:a", "aac", "-b:a", "192k"])
            args.extend(["-movflags", "+faststart", str(output)])
            _run_ffmpeg(args)
        else:
            args = [
                "-i", str(screen_path),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
            ]
            if screen_meta["has_audio"]:
                args.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                args.append("-an")
            args.extend(["-movflags", "+faststart", str(output)])
            _run_ffmpeg(args)

        output_meta = _probe_media(output)
        output_key = project_key(project_id, "video/screen_record.mp4")
        storage_client.write_file(output_key, output, content_type="video/mp4")
        write_json_artifact(
            PROJECTS_DIR / project_id / "video" / "screen_record.json",
            {
                "project_id": project_id,
                "video_path": storage_client.public_url(output_key),
                "duration": output_meta["duration"],
                "width": output_meta["width"],
                "height": output_meta["height"],
                "webcam_overlay": webcam_path is not None,
            },
        )

    return FeatureStubResponse(
        status="complete",
        detail=f"Screen recording created at {storage_client.public_url(output_key)}",
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
