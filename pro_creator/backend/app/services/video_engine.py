from typing import Callable

from app.services.grok_imagine_engine import RenderCancelled, render_grok_imagine_video


def render_video(
    project_id: str,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    return render_grok_imagine_video(project_id, cancel_check=cancel_check)


__all__ = ["RenderCancelled", "render_video"]
