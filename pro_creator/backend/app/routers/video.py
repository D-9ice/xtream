from datetime import datetime
import shutil
import subprocess
import tempfile

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlmodel import Session

import requests
from pathlib import Path

from app.auth import get_current_user
from app.config import CREDITS_COST_VIDEO_EXPORT, CREDITS_COST_VIDEO_RENDER, PROJECTS_DIR
from app.database import get_session
from app.models import User
from app.services.credits import consume_credits, record_usage_event
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
        provider="local",
        model="ffmpeg",
    )
    logger.info("Rendered video for project %s", payload.project_id)
    return VideoResponse(**result)


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
    default_presets = ["youtube", "tiktok", "instagram", "facebook"]
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
