from app.services.grok_imagine_engine import render_grok_imagine_video


def render_video(project_id: str) -> dict:
    return render_grok_imagine_video(project_id)
