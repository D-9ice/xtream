import io

from app.storage import project_key, storage_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


def generate_image_for_scene(project_id: str, scene_id: int, prompt: str, style: str) -> dict:
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (1024, 576), color=(18, 24, 38))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(40, 40), (984, 536)], outline=(34, 211, 238), width=3)
    title = f"Scene {scene_id}"
    subtitle = prompt[:80]
    draw.text((80, 80), title, fill=(226, 232, 240))
    draw.text((80, 140), subtitle, fill=(148, 163, 184))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    key = project_key(project_id, f"images/scene_{scene_id}.png")
    storage_client.write_bytes(key, buffer.getvalue(), content_type="image/png")
    logger.info("Generated image for project %s scene %s", project_id, scene_id)
    return {"image_path": storage_client.public_url(key)}


def generate_image(project_id: str, prompt: str, style: str) -> dict:
    return generate_image_for_scene(project_id, 1, prompt, style)
