import shutil
import subprocess
import tempfile
import time
import base64
from pathlib import Path
import re

import requests

from app.config import (
    FFMPEG_CONCAT_TIMEOUT_SECONDS,
    FFMPEG_SCENE_RENDER_TIMEOUT_SECONDS,
    RUNWAY_API_BASE,
    RUNWAY_API_KEY,
    RUNWAY_API_VERSION,
    RUNWAY_HERO_SCENES,
    RUNWAY_POLL_INTERVAL_SECONDS,
    RUNWAY_POLL_TIMEOUT_SECONDS,
    RUNWAY_VIDEO_DURATION_SECONDS,
    RUNWAY_VIDEO_ENABLED,
    RUNWAY_VIDEO_MODEL_DEFAULT,
    RUNWAY_VIDEO_MODEL_PREMIUM,
)
from app.storage import project_key, storage_client
from app.utils.file_manager import read_scene_metadata
from app.utils.logger import get_logger

logger = get_logger(__name__)


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


def _scene_ids_from_metadata(project_id: str) -> list[int]:
    ids = []
    for scene in read_scene_metadata(project_id):
        try:
            if scene.get("id") is not None:
                ids.append(int(scene["id"]))
        except (ValueError, TypeError):
            continue
    return sorted(set(ids))


def _scene_ids_from_storage(project_id: str) -> list[int]:
    pattern = re.compile(rf"^{re.escape(project_id)}/(?:images|audio)/scene_(\d+)\.")
    found = set()
    for key in storage_client.list_keys(f"{project_id}/"):
        match = pattern.match(key)
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def _find_audio_key(project_id: str, scene_id: int) -> str | None:
    for ext in ("wav", "mp3", "ogg", "m4a"):
        key = project_key(project_id, f"audio/scene_{scene_id}.{ext}")
        if storage_client.exists(key):
            return key
    return None


def _resolve_hero_scene_ids(scene_ids: list[int]) -> set[int]:
    if not scene_ids:
        return set()
    hero_ids: set[int] = set()
    rules = [part.strip().lower() for part in RUNWAY_HERO_SCENES.split(",") if part.strip()]
    for rule in rules:
        if rule == "first":
            hero_ids.add(scene_ids[0])
            continue
        if rule == "last":
            hero_ids.add(scene_ids[-1])
            continue
        try:
            hero_ids.add(int(rule))
        except ValueError:
            continue
    return hero_ids


def _select_runway_model(scene_id: int, hero_scene_ids: set[int]) -> str:
    if scene_id in hero_scene_ids:
        return RUNWAY_VIDEO_MODEL_PREMIUM
    return RUNWAY_VIDEO_MODEL_DEFAULT


def _runway_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
        "X-Runway-Version": RUNWAY_API_VERSION,
        "Content-Type": "application/json",
    }


def _build_prompt_image_data_uri(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _runway_create_task(*, image_bytes: bytes, prompt_text: str, model: str) -> str:
    payload = {
        "model": model,
        "promptImage": _build_prompt_image_data_uri(image_bytes),
        "promptText": prompt_text[:1000],
        "ratio": "1280:720",
        "duration": RUNWAY_VIDEO_DURATION_SECONDS,
    }
    response = requests.post(
        f"{RUNWAY_API_BASE.rstrip('/')}/v1/image_to_video",
        headers=_runway_headers(),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    task = response.json()
    task_id = str(task.get("id", "")).strip()
    if not task_id:
        raise RuntimeError("Runway task creation failed: missing task id")
    return task_id


def _runway_poll_output(task_id: str) -> str:
    deadline = time.time() + RUNWAY_POLL_TIMEOUT_SECONDS
    task_url = f"{RUNWAY_API_BASE.rstrip('/')}/v1/tasks/{task_id}"
    while time.time() < deadline:
        response = requests.get(task_url, headers=_runway_headers(), timeout=30)
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", "")).upper()
        if status in {"SUCCEEDED", "COMPLETED", "SUCCESS"}:
            output = payload.get("output")
            if isinstance(output, list) and output and isinstance(output[0], str):
                return output[0]
            if isinstance(output, str):
                return output
            raise RuntimeError("Runway task succeeded but output URL is missing")
        if status in {"FAILED", "CANCELLED", "ERROR"}:
            detail = payload.get("failure")
            raise RuntimeError(f"Runway task failed: {detail or payload}")
        time.sleep(RUNWAY_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Runway task polling timed out after {RUNWAY_POLL_TIMEOUT_SECONDS}s")


def _download_runway_clip(output_url: str, target_path: Path) -> None:
    response = requests.get(output_url, timeout=120)
    response.raise_for_status()
    target_path.write_bytes(response.content)


def _render_scene_clip_with_runway(
    *,
    ffmpeg_path: str,
    image_bytes: bytes,
    audio_path: Path,
    clip_path: Path,
    scene_text: str,
    model: str,
) -> None:
    task_id = _runway_create_task(
        image_bytes=image_bytes,
        prompt_text=scene_text or "Cinematic scene with natural camera motion",
        model=model,
    )
    output_url = _runway_poll_output(task_id)
    runway_clip_path = clip_path.with_name(f"{clip_path.stem}_runway.mp4")
    _download_runway_clip(output_url, runway_clip_path)

    # Runway clips are short; loop the generated clip to cover narration length.
    _run_ffmpeg_command(
        args=[
            ffmpeg_path,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(runway_clip_path),
            "-i",
            str(audio_path),
            "-vf",
            "scale=1280:720,fps=25,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-shortest",
            str(clip_path),
        ],
        timeout_seconds=FFMPEG_SCENE_RENDER_TIMEOUT_SECONDS,
        phase="scene video assembly",
    )


def _render_scene_clip_with_ffmpeg_image(
    *,
    ffmpeg_path: str,
    image_path: Path,
    audio_path: Path,
    clip_path: Path,
) -> None:
    _run_ffmpeg_command(
        args=[
            ffmpeg_path,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            (
                "[0:v]scale=1280:720,"
                "zoompan=z='min(zoom+0.0008,1.08)':d=125:"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',"
                "fps=25,format=yuv420p[v]"
            ),
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-shortest",
            str(clip_path),
        ],
        timeout_seconds=FFMPEG_SCENE_RENDER_TIMEOUT_SECONDS,
        phase="scene image render",
    )


def _resolve_render_mode(render_provider: str) -> tuple[str, str | None]:
    provider = (render_provider or "ffmpeg").strip().lower()
    if provider in {"ffmpeg", "local"}:
        return ("ffmpeg", None)
    if provider in {"runway_gen4_turbo", "runway-turbo", "gen4_turbo"}:
        return ("runway", RUNWAY_VIDEO_MODEL_DEFAULT)
    if provider in {"runway_gen4_5", "runway-premium", "gen4.5", "gen4_5"}:
        return ("runway", RUNWAY_VIDEO_MODEL_PREMIUM)
    raise ValueError("render_provider must be one of: ffmpeg, runway_gen4_turbo, runway_gen4_5")


def render_video(project_id: str, render_provider: str = "ffmpeg") -> dict:
    key = project_key(project_id, "video/final.mp4")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise ValueError("ffmpeg is required for video rendering but is not installed.")
    mode, fixed_runway_model = _resolve_render_mode(render_provider)
    if mode == "runway":
        if not RUNWAY_VIDEO_ENABLED:
            raise ValueError("Runway rendering is disabled. Set RUNWAY_VIDEO_ENABLED=true.")
        if not RUNWAY_API_KEY.strip():
            raise ValueError("RUNWAY_API_KEY is required for Runway rendering.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_video_") as temp_dir:
        temp_path = Path(temp_dir)
        scenes = read_scene_metadata(project_id)
        scene_ids = _scene_ids_from_metadata(project_id) or _scene_ids_from_storage(project_id)
        scene_text_by_id: dict[int, str] = {}
        for scene in scenes:
            try:
                sid = int(scene.get("id"))
            except (TypeError, ValueError):
                continue
            scene_text_by_id[sid] = str(scene.get("text", "")).strip()
        hero_scene_ids = _resolve_hero_scene_ids(scene_ids) if mode == "runway" and not fixed_runway_model else set()
        if not scene_ids:
            raise ValueError("No scenes found for rendering.")

        clip_paths: list[Path] = []
        for scene_id in scene_ids:
            image_key = project_key(project_id, f"images/scene_{scene_id}.png")
            audio_key = _find_audio_key(project_id, scene_id)
            if not storage_client.exists(image_key) or not audio_key:
                continue

            image_path = temp_path / f"scene_{scene_id}.png"
            audio_path = temp_path / f"scene_{scene_id}{Path(audio_key).suffix}"
            clip_path = temp_path / f"clip_{scene_id}.mp4"
            image_bytes = storage_client.read_bytes(image_key)
            image_path.write_bytes(image_bytes)
            audio_path.write_bytes(storage_client.read_bytes(audio_key))
            used_runway = False
            if mode == "runway":
                model = fixed_runway_model or _select_runway_model(scene_id, hero_scene_ids)
                try:
                    _render_scene_clip_with_runway(
                        ffmpeg_path=ffmpeg_path,
                        image_bytes=image_bytes,
                        audio_path=audio_path,
                        clip_path=clip_path,
                        scene_text=scene_text_by_id.get(scene_id, ""),
                        model=model,
                    )
                    used_runway = True
                    logger.info(
                        "Rendered scene %s via Runway model=%s for project %s",
                        scene_id,
                        model,
                        project_id,
                    )
                except Exception as exc:
                    logger.warning("Runway render failed for project=%s scene=%s, fallback=ffmpeg: %s", project_id, scene_id, exc)

            if not used_runway:
                _render_scene_clip_with_ffmpeg_image(
                    ffmpeg_path=ffmpeg_path,
                    image_path=image_path,
                    audio_path=audio_path,
                    clip_path=clip_path,
                )
            clip_paths.append(clip_path)

        if not clip_paths:
            raise ValueError("Missing required scene image/audio assets for rendering.")

        concat_file = temp_path / "concat.txt"
        concat_file.write_text("\n".join([f"file '{path}'" for path in clip_paths]))
        video_path = temp_path / "final.mp4"
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
                str(video_path),
            ],
            timeout_seconds=FFMPEG_CONCAT_TIMEOUT_SECONDS,
            phase="final video concat",
        )
        video_bytes = video_path.read_bytes()
        storage_client.write_bytes(key, video_bytes, content_type="video/mp4")

    logger.info("Rendered video for project %s with provider=%s", project_id, render_provider)
    return {"video_path": storage_client.public_url(key)}
