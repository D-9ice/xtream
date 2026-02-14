from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from app.config import PROJECTS_DIR, RHUBARB_PATH, RHUBARB_TIMEOUT, AUTO_LIPSYNC
from app.storage import project_key, storage_client
from app.utils.file_manager import (
    read_json_artifact,
    read_scene_metadata,
    read_script,
    write_json_artifact,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_VOWEL_VISEMES = {
    "a": "AA",
    "e": "EH",
    "i": "IH",
    "o": "OW",
    "u": "UH",
    "y": "IH",
}


def fallback_segments(project_id: str) -> list[dict]:
    script = read_script(project_id)
    scenes = read_scene_metadata(project_id)
    cursor = 0.0
    segments = []
    if scenes:
        for idx, scene in enumerate(scenes):
            text = scene.get("text", "")
            duration = max(4.0, len(text.split()) * 0.4)
            segments.append(
                {
                    "segment_id": idx + 1,
                    "start": round(cursor, 2),
                    "end": round(cursor + duration, 2),
                    "text": text,
                }
            )
            cursor += duration
    elif script:
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            duration = max(3.5, len(line.split()) * 0.35)
            segments.append(
                {
                    "segment_id": idx + 1,
                    "start": round(cursor, 2),
                    "end": round(cursor + duration, 2),
                    "text": line,
                }
            )
            cursor += duration
    return segments


def _word_to_viseme(word: str) -> str:
    for char in word.lower():
        if char in _VOWEL_VISEMES:
            return _VOWEL_VISEMES[char]
    return "REST"


def _build_lipsync_timeline(segments: list[dict]) -> list[dict]:
    timeline = []
    for segment in segments:
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        text = segment.get("text", "") or ""
        words = [word for word in text.split() if word.strip()]
        if not words:
            if end <= start:
                end = start + 0.4
            timeline.append(
                {
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "viseme": "REST",
                    "word": "",
                    "segment_id": segment.get("segment_id"),
                }
            )
            continue

        duration = max(0.1, end - start)
        slice_duration = duration / len(words)
        for idx, word in enumerate(words):
            word_start = start + idx * slice_duration
            word_end = word_start + slice_duration
            timeline.append(
                {
                    "start": round(word_start, 2),
                    "end": round(word_end, 2),
                    "viseme": _word_to_viseme(word),
                    "word": word,
                    "segment_id": segment.get("segment_id"),
                }
            )
    return timeline


def _resolve_rhubarb_path() -> str | None:
    if RHUBARB_PATH:
        return RHUBARB_PATH
    return shutil.which("rhubarb")


def _audio_candidates(project_id: str, scene_id: int | None = None) -> Iterable[str]:
    prefix = f"audio/scene_{scene_id}" if scene_id is not None else "audio/scene_1"
    preferred = [
        project_key(project_id, f"{prefix}.wav"),
        project_key(project_id, f"{prefix}.mp3"),
    ]
    for key in preferred:
        yield key
    for key in storage_client.list_keys(f"{project_id}/audio/"):
        if key.endswith((".wav", ".mp3", ".ogg")):
            yield key


def _prepare_audio_file(key: str, tmp_dir: Path) -> Path | None:
    audio_bytes = storage_client.read_bytes(key)
    if not audio_bytes:
        return None
    ext = Path(key).suffix.lower() or ".wav"
    source_path = tmp_dir / f"input{ext}"
    source_path.write_bytes(audio_bytes)
    if ext == ".wav":
        return source_path

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.warning("ffmpeg not found; skipping audio conversion for %s", key)
        return None
    target_path = tmp_dir / "input.wav"
    subprocess.run(
        [ffmpeg_path, "-y", "-i", str(source_path), str(target_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return target_path


def _run_rhubarb(rhubarb_path: str, wav_path: Path, tmp_dir: Path) -> list[dict] | None:
    output_path = tmp_dir / "rhubarb.json"
    try:
        subprocess.run(
            [rhubarb_path, "-f", "json", "-o", str(output_path), str(wav_path)],
            check=True,
            timeout=RHUBARB_TIMEOUT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Rhubarb failed: %s", exc)
        return None

    try:
        data = json.loads(output_path.read_text())
    except json.JSONDecodeError:
        logger.warning("Failed to parse Rhubarb output")
        return None

    timeline = []
    for cue in data.get("mouthCues", []):
        timeline.append(
            {
                "start": round(float(cue.get("start", 0.0)), 2),
                "end": round(float(cue.get("end", 0.0)), 2),
                "viseme": cue.get("value", "REST"),
                "word": "",
                "segment_id": None,
            }
        )
    return timeline


def _scene_ids(segments: list[dict], scenes: list[dict]) -> list[int]:
    ids = {segment.get("segment_id") for segment in segments if segment.get("segment_id")}
    ids.update(scene.get("id") for scene in scenes if scene.get("id"))
    cleaned = sorted({int(scene_id) for scene_id in ids if scene_id is not None})
    return cleaned or [1]


def generate_lipsync(project_id: str) -> dict[str, Any]:
    if not AUTO_LIPSYNC:
        return {"scenes": [], "source": "disabled"}

    transcript_path = PROJECTS_DIR / project_id / "video" / "transcript.json"
    segments = read_json_artifact(transcript_path).get("segments", [])
    if not segments:
        segments = fallback_segments(project_id)
        if segments:
            write_json_artifact(transcript_path, {"segments": segments})

    scenes = read_scene_metadata(project_id)
    scene_ids = _scene_ids(segments, scenes)
    rhubarb_path = _resolve_rhubarb_path()

    scene_payloads = []
    scene_sources = set()
    for scene_id in scene_ids:
        scene_segments = [
            segment for segment in segments if segment.get("segment_id") == scene_id
        ]
        if not scene_segments and segments:
            scene_segments = [segment for segment in segments if segment.get("segment_id")]
        timeline = _build_lipsync_timeline(scene_segments)
        source = "heuristic"

        if rhubarb_path:
            for audio_key in _audio_candidates(project_id, scene_id):
                if not storage_client.exists(audio_key):
                    continue
                with tempfile.TemporaryDirectory(prefix="pro_creator_lipsync_") as tmp:
                    wav_path = _prepare_audio_file(audio_key, Path(tmp))
                    if not wav_path:
                        continue
                    rhubarb_timeline = _run_rhubarb(rhubarb_path, wav_path, Path(tmp))
                    if rhubarb_timeline:
                        timeline = rhubarb_timeline
                        source = "rhubarb"
                        break

        scene_sources.add(source)
        scene_payloads.append(
            {
                "scene_id": scene_id,
                "source": source,
                "visemes": timeline,
            }
        )

    overall_source = "rhubarb" if scene_sources == {"rhubarb"} else "mixed"
    if scene_sources == {"heuristic"}:
        overall_source = "heuristic"
    if not scene_sources:
        overall_source = "disabled"

    combined = [cue for scene in scene_payloads for cue in scene.get("visemes", [])]
    lipsync_path = PROJECTS_DIR / project_id / "video" / "lipsync.json"
    payload = {
        "scenes": scene_payloads,
        "visemes": combined,
        "source": overall_source,
    }
    write_json_artifact(lipsync_path, payload)
    return payload
