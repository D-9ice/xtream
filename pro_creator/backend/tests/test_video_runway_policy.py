import subprocess

from app.services import video_engine


def test_resolve_hero_scene_ids_first_last(monkeypatch):
    monkeypatch.setattr(video_engine, "RUNWAY_HERO_SCENES", "first,last")
    hero = video_engine._resolve_hero_scene_ids([3, 5, 9, 11])
    assert hero == {3, 11}


def test_resolve_hero_scene_ids_numeric_and_keywords(monkeypatch):
    monkeypatch.setattr(video_engine, "RUNWAY_HERO_SCENES", "first,7,last,999")
    hero = video_engine._resolve_hero_scene_ids([2, 7, 8])
    assert hero == {2, 7, 8, 999}


def test_select_runway_model_default_vs_premium(monkeypatch):
    monkeypatch.setattr(video_engine, "RUNWAY_VIDEO_MODEL_DEFAULT", "gen4_turbo")
    monkeypatch.setattr(video_engine, "RUNWAY_VIDEO_MODEL_PREMIUM", "gen4.5")
    hero_scene_ids = {1, 4}

    assert video_engine._select_runway_model(1, hero_scene_ids) == "gen4.5"
    assert video_engine._select_runway_model(4, hero_scene_ids) == "gen4.5"
    assert video_engine._select_runway_model(2, hero_scene_ids) == "gen4_turbo"


def test_resolve_render_mode_explicit_switches(monkeypatch):
    monkeypatch.setattr(video_engine, "RUNWAY_VIDEO_MODEL_DEFAULT", "gen4_turbo")
    monkeypatch.setattr(video_engine, "RUNWAY_VIDEO_MODEL_PREMIUM", "gen4.5")

    assert video_engine._resolve_render_mode("ffmpeg") == ("ffmpeg", None)
    assert video_engine._resolve_render_mode("runway_gen4_turbo") == ("runway", "gen4_turbo")
    assert video_engine._resolve_render_mode("runway_gen4_5") == ("runway", "gen4.5")


def test_run_ffmpeg_command_wraps_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=12)

    monkeypatch.setattr(video_engine.subprocess, "run", fake_run)

    try:
        video_engine._run_ffmpeg_command(
            args=["ffmpeg", "-version"],
            timeout_seconds=12,
            phase="final video concat",
        )
    except RuntimeError as exc:
        assert str(exc) == "ffmpeg timed out during final video concat after 12s"
    else:
        raise AssertionError("Expected ffmpeg timeout to raise RuntimeError")
