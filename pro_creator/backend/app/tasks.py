from app.celery_app import celery_app
from app.services.script_engine import generate_script
from app.services.lipsync_engine import generate_lipsync
from app.services.voice_engine import generate_voice_for_scene
from app.services.image_engine import generate_image_for_scene
from app.services.video_engine import render_video
from app.utils.file_manager import ensure_project_dirs, write_scene_metadata, write_script
from app.utils.file_manager import read_scene_metadata
from app.schemas import ExportPresetRequest
from app.routers.video import export_preset


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

    voice_outputs: list[dict] = []
    image_outputs: list[dict] = []
    for idx, scene in enumerate(scenes, start=1):
        scene_id = int(scene.get("id", idx))
        scene_text = str(scene.get("text", "")).strip()
        voice_input = voice_text or scene_text or topic or "Narration"
        image_input = image_prompt or scene_text or topic or "Visual concept"
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
