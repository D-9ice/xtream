from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import requests

from app.config import (
    FFMPEG_CONCAT_TIMEOUT_SECONDS,
    GROK_IMAGINE_ASPECT_RATIO,
    GROK_IMAGINE_EXTENSION_CHUNK_SECONDS,
    GROK_IMAGINE_INITIAL_CHUNK_SECONDS,
    GROK_IMAGINE_MAX_CLIP_BYTES,
    GROK_IMAGINE_POLL_INTERVAL_SECONDS,
    GROK_IMAGINE_POLL_TIMEOUT_SECONDS,
    GROK_IMAGINE_RESOLUTION,
    GROK_IMAGINE_TARGET_SEGMENT_SECONDS,
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_VIDEO_MODEL,
)
from app.storage import project_key, storage_client
from app.utils.file_manager import read_scene_metadata, read_script
from app.utils.logger import get_logger

logger = get_logger(__name__)


class _RetryableGenerationError(RuntimeError):
    pass


class RenderCancelled(RuntimeError):
    """Raised when a caller requests cancellation during Grok rendering."""


def _check_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise RenderCancelled("Grok Imagine rendering was cancelled.")


def _sleep_with_cancel(seconds: float, cancel_check: Callable[[], bool] | None) -> None:
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        _check_cancelled(cancel_check)
        time.sleep(min(0.5, max(0.0, deadline - time.time())))
    _check_cancelled(cancel_check)


def _run_ffmpeg_command(*, args: list[str], timeout_seconds: int, phase: str) -> None:
    try:
        subprocess.run(
            args,
            check=True,
            timeout=timeout_seconds,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffmpeg timed out during {phase} after {timeout_seconds}s") from exc


def _xai_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }


def _load_bundle(project_id: str) -> dict:
    key = project_key(project_id, "workflow/approved_production_bundle.json")
    raw = storage_client.read_text(key)
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse approved production bundle for %s", project_id)
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_scene_texts(project_id: str) -> list[tuple[int, str]]:
    scenes = read_scene_metadata(project_id)
    if scenes:
        rows: list[tuple[int, str]] = []
        for index, item in enumerate(scenes, start=1):
            if not isinstance(item, dict):
                continue
            try:
                scene_id = int(item.get("id") or index)
            except (TypeError, ValueError):
                scene_id = index
            text = str(item.get("text", "")).strip()
            if text:
                rows.append((scene_id, text))
        if rows:
            return rows

    script = read_script(project_id).strip()
    if not script:
        return [(1, "A cinematic dialogue-driven scene")]
    lines = [line.strip() for line in script.splitlines() if line.strip()]
    if not lines:
        return [(1, script[:400])]
    return [(index + 1, line) for index, line in enumerate(lines)]


def _character_context(bundle: dict) -> str:
    characters = bundle.get("characters")
    if not isinstance(characters, list) or not characters:
        return ""

    lines: list[str] = []
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        role_type = str(item.get("role_type", "")).strip()
        description = str(item.get("description", "")).strip()
        identity_hash = str(item.get("identity_hash", "")).strip()
        consistency_seed = str(item.get("consistency_seed", "")).strip()
        refs = item.get("reference_image_urls")
        ref_list = [str(ref).strip() for ref in refs if str(ref).strip()] if isinstance(refs, list) else []
        parts = [part for part in [name, role_type, description] if part]
        if identity_hash:
            parts.append(f"identity_hash={identity_hash}")
        if consistency_seed:
            parts.append(f"seed={consistency_seed}")
        if ref_list:
            parts.append(f"refs={'; '.join(ref_list[:3])}")
        if parts:
            lines.append(" | ".join(parts))
    return "\n".join(lines)


def _build_segment_prompt(
    *,
    project_id: str,
    bundle: dict,
    scene_text: str,
    scene_index: int,
    segment_count: int,
) -> str:
    title = str(bundle.get("project_id", project_id)).strip()
    script = str(bundle.get("approved_script_snapshot") or bundle.get("script") or "").strip()
    start_credits = str(bundle.get("start_credits") or "").strip()
    end_credits = str(bundle.get("end_credits") or "").strip()
    characters = _character_context(bundle)
    reference_notes = bundle.get("reference_bundles")
    reference_text = ""
    if isinstance(reference_notes, dict) and reference_notes:
        compact: list[str] = []
        for character_id, refs in reference_notes.items():
            if not isinstance(refs, list):
                continue
            cleaned = [str(ref).strip() for ref in refs if str(ref).strip()]
            if cleaned:
                compact.append(f"{character_id}: {', '.join(cleaned[:2])}")
        reference_text = "\n".join(compact)

    prompt_lines: list[str] = []
    normalized_scene_text = scene_text.lower()
    if normalized_scene_text.startswith("__credits_start__") or normalized_scene_text.startswith("opening credits:"):
        prompt_lines.extend(
            [
                "Generate a polished opening credits sequence.",
                f"Segment {scene_index}/{segment_count}. Show the title card, credited cast, and production crew with a studio-grade opening feel.",
                "Keep the composition elegant, cinematic, and easy to read.",
            ]
        )
        if start_credits:
            prompt_lines.append(f"Opening credits text:\n{start_credits}")
    elif normalized_scene_text.startswith("__credits_end__") or normalized_scene_text.startswith("end credits:"):
        prompt_lines.extend(
            [
                "Generate a polished closing credits sequence.",
                f"Segment {scene_index}/{segment_count}. Present a rolling or autoscrolling end-credit card that follows the film cleanly.",
                "Keep the composition elegant, cinematic, and easy to read.",
            ]
        )
        if end_credits:
            prompt_lines.append(f"End credits text:\n{end_credits}")
    else:
        prompt_lines.extend(
            [
                "Generate a cinematic, dialogue-driven video segment that continues the project seamlessly.",
                f"Segment {scene_index}/{segment_count}. Keep the same cast, tone, wardrobe, and camera language across the entire segment.",
                "The clip must feel like a direct continuation of the previous frame when a source image is provided.",
            ]
        )
    if title:
        prompt_lines.append(f"Project: {title}")
    if script:
        prompt_lines.append(f"Approved script:\n{script[:3000]}")
    if scene_text:
        prompt_lines.append(f"Segment focus:\n{scene_text[:2000]}")
    if characters:
        prompt_lines.append(f"Cast continuity rules:\n{characters[:3000]}")
    if reference_text:
        prompt_lines.append(f"Reference imagery:\n{reference_text[:2000]}")
    prompt_lines.extend(
        [
            "Audio should match the visual beat naturally and support spoken dialogue if present.",
            "Avoid abrupt changes in lighting, framing, or character identity.",
        ]
    )
    return "\n\n".join(prompt_lines)


def _start_video_generation(
    *,
    prompt: str,
    duration: int,
    prompt_image_bytes: bytes | None = None,
) -> str:
    payload: dict[str, object] = {
        "model": XAI_VIDEO_MODEL,
        "prompt": prompt[:4000],
        "duration": duration,
        "aspect_ratio": GROK_IMAGINE_ASPECT_RATIO,
        "resolution": GROK_IMAGINE_RESOLUTION,
    }
    if prompt_image_bytes is not None:
        payload["image"] = {
            "url": f"data:image/png;base64,{base64.b64encode(prompt_image_bytes).decode('ascii')}"
        }
    response = requests.post(
        f"{XAI_BASE_URL}/videos/generations",
        headers=_xai_headers(),
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    body = response.json()
    request_id = (
        str(body.get("request_id") or body.get("requestId") or body.get("id") or "").strip()
    )
    if not request_id:
        raise RuntimeError(f"xAI video generation did not return a request id: {body}")
    return request_id


def _poll_video_url(request_id: str, cancel_check: Callable[[], bool] | None = None) -> str:
    deadline = time.time() + GROK_IMAGINE_POLL_TIMEOUT_SECONDS
    last_poll_error: Exception | None = None
    while time.time() < deadline:
        _check_cancelled(cancel_check)
        try:
            response = requests.get(
                f"{XAI_BASE_URL}/videos/{request_id}",
                headers=_xai_headers(),
                timeout=60,
            )
            if response.status_code == 429 or response.status_code >= 500:
                last_poll_error = RuntimeError(f"xAI poll HTTP {response.status_code}")
                _sleep_with_cancel(GROK_IMAGINE_POLL_INTERVAL_SECONDS, cancel_check)
                continue
            response.raise_for_status()
            payload = response.json()
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_poll_error = exc
            _sleep_with_cancel(GROK_IMAGINE_POLL_INTERVAL_SECONDS, cancel_check)
            continue

        status = str(payload.get("status") or payload.get("state") or "").lower()
        if status in {"done", "succeeded", "completed", "success"}:
            video = payload.get("video")
            if isinstance(video, dict):
                for key in ("url", "video_url", "output_url"):
                    value = video.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            for key in ("url", "video_url", "output_url"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            output = payload.get("output")
            if isinstance(output, str) and output.strip():
                return output.strip()
            if isinstance(output, list) and output:
                first = output[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
            raise RuntimeError(f"xAI video generation completed without a result URL: {payload}")
        if status in {"failed", "expired", "cancelled", "error"}:
            error = payload.get("error")
            error_code = ""
            if isinstance(error, dict):
                error_code = str(error.get("code") or "").lower()
            if error_code in {"service_unavailable", "internal_error"}:
                raise _RetryableGenerationError(
                    f"xAI video generation failed transiently [{error_code}] for request {request_id}"
                )
            raise RuntimeError(f"xAI video generation failed: {payload}")
        _sleep_with_cancel(GROK_IMAGINE_POLL_INTERVAL_SECONDS, cancel_check)

    suffix = f"; last poll error: {last_poll_error}" if last_poll_error else ""
    raise TimeoutError(
        f"xAI video generation timed out after {GROK_IMAGINE_POLL_TIMEOUT_SECONDS}s "
        f"for request {request_id}{suffix}"
    )


def _validate_video_file(path: Path) -> None:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("ffprobe is required to validate Grok Imagine output.")
    try:
        result = subprocess.run(
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
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Grok Imagine video validation failed.") from exc
    if result.returncode != 0 or "video" not in result.stdout.lower():
        raise RuntimeError("Grok Imagine returned an invalid video file.")


def _download_video(url: str, target_path: Path, cancel_check: Callable[[], bool] | None = None) -> None:
    last_error: Exception | None = None
    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        _check_cancelled(cancel_check)
        total = 0
        try:
            with requests.get(url, stream=True, timeout=(10, 240)) as response:
                response.raise_for_status()
                with target_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        _check_cancelled(cancel_check)
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > GROK_IMAGINE_MAX_CLIP_BYTES:
                            raise RuntimeError("Grok Imagine clip exceeded the configured size limit.")
                        handle.write(chunk)
            if total == 0:
                raise RuntimeError("Grok Imagine returned an empty video file.")
            _validate_video_file(target_path)
            return
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            target_path.unlink(missing_ok=True)
            if attempt < attempts:
                _sleep_with_cancel(PROVIDER_RETRY_BACKOFF_SECONDS * attempt, cancel_check)
    raise RuntimeError(f"Failed to download Grok Imagine video: {last_error}")


def _extract_last_frame(ffmpeg_path: str, video_path: Path, frame_path: Path) -> None:
    _run_ffmpeg_command(
        args=[
            ffmpeg_path,
            "-y",
            "-sseof",
            "-0.1",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(frame_path),
        ],
        timeout_seconds=60,
        phase="last frame extraction",
    )


def _concat_videos(ffmpeg_path: str, clip_paths: list[Path], output_path: Path) -> None:
    concat_file = output_path.with_suffix(".txt")
    concat_file.write_text("\n".join([f"file '{path}'" for path in clip_paths]))
    _run_ffmpeg_command(
        args=[
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_path),
        ],
        timeout_seconds=FFMPEG_CONCAT_TIMEOUT_SECONDS,
        phase="video concat",
    )


def _duration_plan(target_seconds: int) -> list[int]:
    remaining = max(1, int(target_seconds))
    plan: list[int] = []
    first = min(GROK_IMAGINE_INITIAL_CHUNK_SECONDS, remaining)
    plan.append(first)
    remaining -= first
    while remaining > 0:
        chunk = min(GROK_IMAGINE_EXTENSION_CHUNK_SECONDS, remaining)
        plan.append(chunk)
        remaining -= chunk
    return plan


def _render_segment(
    *,
    ffmpeg_path: str,
    project_id: str,
    bundle: dict,
    scene_text: str,
    scene_index: int,
    total_segments: int,
    temp_path: Path,
    initial_frame_bytes: bytes | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[Path, bytes | None]:
    clip_paths: list[Path] = []
    prompt_image: bytes | None = initial_frame_bytes
    segment_prompt = _build_segment_prompt(
        project_id=project_id,
        bundle=bundle,
        scene_text=scene_text,
        scene_index=scene_index,
        segment_count=total_segments,
    )
    chunk_plan = _duration_plan(GROK_IMAGINE_TARGET_SEGMENT_SECONDS)
    for chunk_index, chunk_seconds in enumerate(chunk_plan, start=1):
        _check_cancelled(cancel_check)
        prompt = segment_prompt
        if prompt_image is not None:
            prompt = (
                segment_prompt
                + "\n\n"
                + "Continue from the provided source frame. "
                "Preserve pose, lighting, and identity while advancing the action."
            )
        clip_path = temp_path / f"segment_{scene_index}_{chunk_index}.mp4"
        generation_attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
        last_generation_error: Exception | None = None
        for generation_attempt in range(1, generation_attempts + 1):
            _check_cancelled(cancel_check)
            try:
                request_id = _start_video_generation(
                    prompt=prompt,
                    duration=chunk_seconds,
                    prompt_image_bytes=prompt_image,
                )
                logger.info(
                    "Started Grok Imagine request %s for project=%s scene=%s chunk=%s",
                    request_id,
                    project_id,
                    scene_index,
                    chunk_index,
                )
                clip_url = _poll_video_url(request_id, cancel_check=cancel_check)
                _download_video(clip_url, clip_path, cancel_check=cancel_check)
                last_generation_error = None
                break
            except _RetryableGenerationError as exc:
                last_generation_error = exc
                if generation_attempt < generation_attempts:
                    _sleep_with_cancel(PROVIDER_RETRY_BACKOFF_SECONDS * generation_attempt, cancel_check)
                    continue
                raise
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in {429, 500, 502, 503, 504} and generation_attempt < generation_attempts:
                    last_generation_error = exc
                    _sleep_with_cancel(PROVIDER_RETRY_BACKOFF_SECONDS * generation_attempt, cancel_check)
                    continue
                raise
        if last_generation_error is not None:
            raise last_generation_error
        _check_cancelled(cancel_check)
        clip_paths.append(clip_path)
        if chunk_index < len(chunk_plan):
            frame_path = temp_path / f"segment_{scene_index}_{chunk_index}.png"
            _extract_last_frame(ffmpeg_path, clip_path, frame_path)
            prompt_image = frame_path.read_bytes()

    if len(clip_paths) == 1:
        final_segment_path = clip_paths[0]
    else:
        final_segment_path = temp_path / f"segment_{scene_index}.mp4"
        _concat_videos(ffmpeg_path, clip_paths, final_segment_path)

    final_frame_path = temp_path / f"segment_{scene_index}_final.png"
    _extract_last_frame(ffmpeg_path, final_segment_path, final_frame_path)
    return final_segment_path, final_frame_path.read_bytes()


def render_grok_imagine_video(project_id: str, cancel_check: Callable[[], bool] | None = None) -> dict:
    _check_cancelled(cancel_check)
    api_key = XAI_API_KEY.strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is required for Grok Imagine video rendering.")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise ValueError("ffmpeg is required for Grok Imagine video stitching but is not installed.")

    bundle = _load_bundle(project_id)
    scenes = _load_scene_texts(project_id)
    if not scenes:
        raise ValueError("No scenes found for Grok Imagine rendering.")
    render_sequence: list[tuple[int, str]] = []
    start_credits = str(bundle.get("start_credits") or "").strip()
    end_credits = str(bundle.get("end_credits") or "").strip()
    if start_credits:
        render_sequence.append((0, f"__CREDITS_START__\n{start_credits}"))
    render_sequence.extend(scenes)
    if end_credits:
        render_sequence.append((len(render_sequence) + 1, f"__CREDITS_END__\n{end_credits}"))

    with tempfile.TemporaryDirectory(prefix="pro_creator_grok_imagine_") as temp_dir:
        temp_path = Path(temp_dir)
        segment_paths: list[Path] = []
        scene_count = len(render_sequence)
        previous_frame_bytes: bytes | None = None
        for scene_index, (_, scene_text) in enumerate(render_sequence, start=1):
            _check_cancelled(cancel_check)
            segment_path, previous_frame_bytes = _render_segment(
                ffmpeg_path=ffmpeg_path,
                project_id=project_id,
                bundle=bundle,
                scene_text=scene_text,
                scene_index=scene_index,
                total_segments=scene_count,
                temp_path=temp_path,
                initial_frame_bytes=previous_frame_bytes,
                cancel_check=cancel_check,
            )
            segment_paths.append(segment_path)

        _check_cancelled(cancel_check)
        if not segment_paths:
            raise ValueError("Grok Imagine rendering produced no clips.")

        final_path = temp_path / "final.mp4"
        if len(segment_paths) == 1:
            final_path.write_bytes(segment_paths[0].read_bytes())
        else:
            _concat_videos(ffmpeg_path, segment_paths, final_path)

        _check_cancelled(cancel_check)
        _validate_video_file(final_path)
        _check_cancelled(cancel_check)
        video_key = project_key(project_id, "video/final.mp4")
        storage_client.write_file(video_key, final_path, content_type="video/mp4")

        plan_key = project_key(project_id, "workflow/grok_imagine_plan.json")
        storage_client.write_text(
            plan_key,
            json.dumps(
                {
                    "project_id": project_id,
                    "model": XAI_VIDEO_MODEL,
                    "segment_seconds": GROK_IMAGINE_TARGET_SEGMENT_SECONDS,
                    "segments": scene_count,
                },
                indent=2,
            ),
        )

    logger.info("Rendered Grok Imagine video for project %s", project_id)
    return {"video_path": storage_client.public_url(video_key)}
