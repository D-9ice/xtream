from sqlmodel import Session

from app.celery_app import celery_app
from app.database import engine
from app.models import OrchestrationJob
from app.services.script_engine import generate_script
from app.services.lipsync_engine import generate_lipsync
from app.services.voice_engine import generate_voice_bytes, generate_voice_for_scene
from app.services.image_engine import generate_image_for_scene
from app.services.video_engine import render_video
from app.services.workflow_service import execute_workflow_production_job
from app.utils.file_manager import ensure_project_dirs, write_scene_metadata, write_script
from app.utils.file_manager import read_scene_metadata
from app.utils.file_manager import read_character_voice_profiles
from app.schemas import ExportPresetRequest
from app.routers.video import export_preset
from app.storage import storage_client

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


@celery_app.task(name="pro_creator.generate_script")
def generate_script_task(project_id: str, topic: str, duration_minutes: float, tone: str) -> dict:
    result = generate_script(topic, duration_minutes, tone)
    project_path = ensure_project_dirs(project_id)
    write_script(project_path, result["full_script"])
    write_scene_metadata(project_path, result["scenes"])
    return result


@celery_app.task(name="pro_creator.generate_voice")
def generate_voice_task(project_id: str, text: str, scene_id: int = 1) -> dict:
    result = generate_voice_for_scene(project_id, scene_id, text)
    try:
        generate_lipsync(project_id)
    except Exception as exc:
        return {"warning": f"Lip sync failed: {exc}", **result}
    return result


@celery_app.task(name="pro_creator.generate_image")
def generate_image_task(project_id: str, prompt: str, style: str, scene_id: int = 1) -> dict:
    return generate_image_for_scene(project_id, scene_id, prompt, style)


@celery_app.task(name="pro_creator.render_video")
def render_video_task(project_id: str) -> dict:
    return render_video(project_id)


@celery_app.task(name="pro_creator.export_preset")
def export_preset_task(project_id: str, preset: str) -> dict:
    response = export_preset(ExportPresetRequest(project_id=project_id, preset=preset))
    return {"export_path": response.export_path}


@celery_app.task(name="pro_creator.workflow_production")
def workflow_production_task(job_id: int) -> dict:
    with Session(engine) as session:
        job = session.get(OrchestrationJob, job_id)
        if not job:
            raise ValueError(f"Workflow production job {job_id} not found")
        video_path = execute_workflow_production_job(session=session, job=job)
        return {"video_path": video_path}


@celery_app.task(name="pro_creator.full_pipeline")
def full_pipeline_task(
    project_id: str,
    topic: str,
    duration_minutes: float,
    tone: str,
    export_preset_name: str = "youtube",
    voice_text: str | None = None,
    image_prompt: str | None = None,
) -> dict:
    script_result = generate_script(topic, duration_minutes, tone)
    project_path = ensure_project_dirs(project_id)
    write_script(project_path, script_result["full_script"])
    write_scene_metadata(project_path, script_result["scenes"])

    scenes = read_scene_metadata(project_id)
    if not scenes:
        scenes = [{"id": 1, "text": voice_text or topic or "Narration"}]

    def _extract_dialogue_lines(scene_text: str) -> list[tuple[str, str]]:
        dialogue: list[tuple[str, str]] = []
        for raw_line in (scene_text or "").splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            if line.lower().startswith(("scene ", "intent:", "narration:", "visuals:")):
                continue
            speaker, text_line = line.split(":", 1)
            speaker = speaker.strip()
            text_line = text_line.strip()
            if not speaker or not text_line:
                continue
            if len(speaker) > 24 or re.search(r"\s{2,}", speaker):
                continue
            dialogue.append((speaker, text_line))
        return dialogue

    def _render_dialogue_scene(scene_id: int, dialogue: list[tuple[str, str]]) -> str:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return generate_voice_for_scene(project_id, scene_id, " ".join(t for _, t in dialogue))["audio_path"]
        character_map = {
            str(item.get("character_id", "")).strip(): item
            for item in read_character_voice_profiles(project_id)
            if isinstance(item, dict)
        }
        with tempfile.TemporaryDirectory(prefix="pro_creator_task_dialogue_") as temp_dir:
            temp_path = Path(temp_dir)
            parts: list[Path] = []
            idx = 0
            for speaker, text_line in dialogue:
                mapped = character_map.get(speaker, {})
                audio_bytes, ext, _content_type = generate_voice_bytes(
                    project_id=project_id,
                    text=text_line,
                    voice_profile=mapped.get("voice_profile") or "default",
                    provider=mapped.get("tts_provider"),
                    override_voice_id=mapped.get("voice_id"),
                )
                seg_path = temp_path / f"seg_{idx}.{ext}"
                seg_path.write_bytes(audio_bytes)
                parts.append(seg_path)
                idx += 1
                pause_path = temp_path / f"pause_{idx}.wav"
                subprocess.run(
                    [
                        ffmpeg_path,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=22050:cl=mono",
                        "-t",
                        "0.20",
                        str(pause_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                parts.append(pause_path)
                idx += 1

            concat_path = temp_path / "concat.txt"
            concat_path.write_text("\n".join([f"file '{p}'" for p in parts]), encoding="utf-8")
            out_path = temp_path / f"scene_{scene_id}.m4a"
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-c:a",
                    "aac",
                    str(out_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            key = f"{project_id}/audio/scene_{scene_id}.m4a"
            storage_client.write_bytes(key, out_path.read_bytes(), content_type="audio/mp4")
            return storage_client.public_url(key)

    voice_outputs: list[dict] = []
    image_outputs: list[dict] = []
    for idx, scene in enumerate(scenes, start=1):
        scene_id = int(scene.get("id", idx))
        scene_text = str(scene.get("text", "")).strip()
        voice_input = voice_text or scene_text or topic or "Narration"
        image_input = image_prompt or scene_text or topic or "Visual concept"
        dialogue = _extract_dialogue_lines(scene_text)
        if len(dialogue) >= 2 and len({speaker.lower() for speaker, _ in dialogue}) >= 2:
            voice_outputs.append(
                {"audio_path": _render_dialogue_scene(scene_id, dialogue), "duration_seconds": max(2.0, len(dialogue))}
            )
        else:
            voice_outputs.append(generate_voice_for_scene(project_id, scene_id, voice_input))
        image_outputs.append(generate_image_for_scene(project_id, scene_id, image_input, "cinematic"))

    video_output = render_video(project_id)
    export_output = export_preset(
        ExportPresetRequest(project_id=project_id, preset=export_preset_name)
    )
    return {
        "script": script_result,
        "voice": voice_outputs,
        "image": image_outputs,
        "video": video_output,
        "export_path": export_output.export_path,
    }
