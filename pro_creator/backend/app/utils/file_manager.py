from pathlib import Path
from typing import List
import json
import os
import shutil

from app.config import PROJECTS_DIR
from app.storage import project_key, storage_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_project_dirs(project_id: str) -> Path:
    return storage_client.ensure_project_dirs(project_id)


def write_script(project_path: Path, script: str) -> None:
    key = project_key(project_path.name, "script.txt")
    storage_client.write_text(key, script)
    logger.info("Saved script to %s", key)


def write_scene_metadata(project_path: Path, scenes: List[dict]) -> None:
    import json

    key = project_key(project_path.name, "scenes.json")
    storage_client.write_text(key, json.dumps(scenes, indent=2))
    logger.info("Saved scenes to %s", key)


def read_script(project_id: str) -> str:
    key = project_key(project_id, "script.txt")
    return storage_client.read_text(key)


def read_scene_metadata(project_id: str) -> List[dict]:
    import json

    key = project_key(project_id, "scenes.json")
    content = storage_client.read_text(key)
    if not content:
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse scenes.json for %s", project_id)
        return []


def clear_script_assets(project_id: str) -> None:
    script_key = project_key(project_id, "script.txt")
    scenes_key = project_key(project_id, "scenes.json")
    storage_client.write_text(script_key, "")
    storage_client.write_text(scenes_key, "")
    logger.info("Cleared script assets for %s", project_id)


def delete_project_dir(project_id: str) -> None:
    """
    Best-effort cleanup.

    Deleting a project should not fail just because the on-disk directory (or an
    object-store prefix) can't be fully removed.
    """

    def _rmtree_best_effort(path: Path) -> None:
        def _onerror(func, p, _exc_info):
            # Retry after making the path writable (common when deleting read-only artifacts).
            try:
                os.chmod(p, 0o700)
                func(p)
            except Exception:
                raise

        shutil.rmtree(path, onerror=_onerror)

    try:
        if storage_client.backend == "s3":
            storage_client.delete_prefix(f"{project_id}/")
        else:
            project_path = PROJECTS_DIR / project_id
            if project_path.exists():
                _rmtree_best_effort(project_path)
        logger.info("Deleted project directory for %s", project_id)
    except Exception:
        logger.warning(
            "Failed to delete project directory for %s (continuing)", project_id, exc_info=True
        )


def project_has_assets(project_id: str) -> bool:
    script_text = read_script(project_id).strip()
    if script_text:
        return True
    scenes = read_scene_metadata(project_id)
    if scenes:
        return True
    prefix = f"{project_id}/"
    for key in storage_client.list_keys(prefix):
        if any(folder in key for folder in ["audio/", "images/", "video/", "voice_profiles/"]):
            return True
    return False


def save_voice_profile(project_id: str, profile_name: str, content: bytes) -> Path:
    key = project_key(project_id, f"voice_profiles/{profile_name}.wav")
    storage_client.write_bytes(key, content, content_type="audio/wav")
    logger.info("Saved voice profile to %s", key)
    return PROJECTS_DIR / key


def _voice_metadata_key(project_id: str) -> str:
    return project_key(project_id, "voice_profiles/metadata.json")


def _character_metadata_key(project_id: str) -> str:
    return project_key(project_id, "voice_profiles/characters.json")


def read_voice_profile_metadata(project_id: str) -> dict:
    content = storage_client.read_text(_voice_metadata_key(project_id))
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse voice metadata for %s", project_id)
        return {}


def write_voice_profile_metadata(project_id: str, payload: dict) -> None:
    storage_client.write_text(_voice_metadata_key(project_id), json.dumps(payload, indent=2))


def update_voice_profile_metadata(project_id: str, profile_name: str, payload: dict) -> None:
    metadata = read_voice_profile_metadata(project_id)
    metadata[profile_name] = payload
    write_voice_profile_metadata(project_id, metadata)


def delete_voice_profile_metadata(project_id: str, profile_name: str) -> None:
    metadata = read_voice_profile_metadata(project_id)
    if profile_name in metadata:
        metadata.pop(profile_name, None)
        write_voice_profile_metadata(project_id, metadata)


def list_voice_profiles(project_id: str) -> List[str]:
    prefix = f"{project_id}/voice_profiles/"
    profiles = []
    for key in storage_client.list_keys(prefix):
        if key.endswith(".wav"):
            profiles.append(Path(key).stem)
    metadata = read_voice_profile_metadata(project_id)
    profiles.extend(list(metadata.keys()))
    return sorted(set(profiles))


def delete_voice_profile(project_id: str, profile_name: str) -> bool:
    key = project_key(project_id, f"voice_profiles/{profile_name}.wav")
    if storage_client.exists(key):
        storage_client.delete_key(key)
        logger.info("Deleted voice profile %s for project %s", profile_name, project_id)
        delete_voice_profile_metadata(project_id, profile_name)
        return True
    delete_voice_profile_metadata(project_id, profile_name)
    return False


def read_character_voice_profiles(project_id: str) -> list[dict]:
    content = storage_client.read_text(_character_metadata_key(project_id))
    if not content:
        return []
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse character voice metadata for %s", project_id)
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def write_character_voice_profiles(project_id: str, characters: list[dict]) -> None:
    storage_client.write_text(
        _character_metadata_key(project_id),
        json.dumps(characters, indent=2),
    )


def upsert_character_voice_profile(project_id: str, payload: dict) -> list[dict]:
    character_id = str(payload.get("character_id", "")).strip()
    if not character_id:
        return read_character_voice_profiles(project_id)
    existing = read_character_voice_profiles(project_id)
    next_items: list[dict] = []
    replaced = False
    for item in existing:
        if str(item.get("character_id", "")).strip() == character_id:
            next_items.append(payload)
            replaced = True
        else:
            next_items.append(item)
    if not replaced:
        next_items.append(payload)
    write_character_voice_profiles(project_id, next_items)
    return next_items


def delete_character_voice_profile(project_id: str, character_id: str) -> list[dict]:
    target = character_id.strip()
    existing = read_character_voice_profiles(project_id)
    next_items = [
        item
        for item in existing
        if str(item.get("character_id", "")).strip() != target
    ]
    write_character_voice_profiles(project_id, next_items)
    return next_items


def write_json_artifact(path: Path, payload: dict | list) -> None:
    key = str(path.relative_to(PROJECTS_DIR))
    storage_client.write_text(key, json.dumps(payload, indent=2))
    logger.info("Saved artifact to %s", key)


def read_json_artifact(path: Path) -> dict:
    key = str(path.relative_to(PROJECTS_DIR))
    content = storage_client.read_text(key)
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse artifact %s", key)
        return {}
