import shutil
import subprocess
import tempfile
from pathlib import Path
import re

from app.storage import project_key, storage_client
from app.utils.file_manager import read_scene_metadata
from app.utils.logger import get_logger

logger = get_logger(__name__)


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


def render_video(project_id: str) -> dict:
    key = project_key(project_id, "video/final.mp4")
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise ValueError("ffmpeg is required for video rendering but is not installed.")

    with tempfile.TemporaryDirectory(prefix="pro_creator_video_") as temp_dir:
        temp_path = Path(temp_dir)
        scene_ids = _scene_ids_from_metadata(project_id) or _scene_ids_from_storage(project_id)
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
            image_path.write_bytes(storage_client.read_bytes(image_key))
            audio_path.write_bytes(storage_client.read_bytes(audio_key))

            subprocess.run(
                [
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
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            clip_paths.append(clip_path)

        if not clip_paths:
            raise ValueError("Missing required scene image/audio assets for rendering.")

        concat_file = temp_path / "concat.txt"
        concat_file.write_text("\n".join([f"file '{path}'" for path in clip_paths]))
        video_path = temp_path / "final.mp4"
        subprocess.run(
            [
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
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        video_bytes = video_path.read_bytes()
        storage_client.write_bytes(key, video_bytes, content_type="video/mp4")

    logger.info("Rendered video for project %s", project_id)
    return {"video_path": storage_client.public_url(key)}
