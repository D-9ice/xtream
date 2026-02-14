from app.celery_app import celery_app
from app.services.script_engine import generate_script
from app.services.lipsync_engine import generate_lipsync
from app.services.voice_engine import generate_voice_for_scene
from app.services.image_engine import generate_image_for_scene
from app.services.video_engine import render_video
from app.utils.file_manager import ensure_project_dirs, write_scene_metadata, write_script
from app.schemas import ExportPresetRequest
from app.routers.video import export_preset


@celery_app.task(name="pro_creator.generate_script")
def generate_script_task(project_id: str, topic: str, duration_minutes: int, tone: str) -> dict:
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
