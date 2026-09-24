import app.services.script_engine as script_engine

from app.services.script_engine import _build_script_blueprint, _parse_script_brief


def test_parse_script_brief_supports_inline_title_prompt() -> None:
    raw = (
        "Title: Promotional Ad for Pro Creator App "
        "Prompt: Create a one-minute ad for Pro Creator that covers script, voice, image, and video."
    )
    title, prompt = _parse_script_brief(raw)
    assert title == "Promotional Ad for Pro Creator App"
    assert "one-minute ad for Pro Creator" in prompt


def test_parse_script_brief_supports_inline_without_colons() -> None:
    raw = (
        "Title Promotional Ad for Pro Creator App "
        "Prompt Create a one-minute ad for Pro Creator that covers script, voice, image, and video."
    )
    title, prompt = _parse_script_brief(raw)
    assert title == "Promotional Ad for Pro Creator App"
    assert prompt.startswith("Create a one-minute ad for Pro Creator")


def test_script_blueprint_includes_strict_directives() -> None:
    blueprint = _build_script_blueprint(
        title="Skyline Rescue",
        prompt="A rescue mission under moonlight.",
        tone="cinematic",
        duration_minutes=4,
        genre="Adventure",
        factual_mode=False,
        scene_count=4,
    )
    combined = "\n".join(blueprint).lower()
    assert "bulletproof" in combined
    assert "single-character dna" in combined
    assert "multi-character dna" in combined
    assert "genre adherence" in combined
    assert "duration adherence" in combined
    assert "word-count adherence" in combined


def test_true_story_passes_research_context_to_xai(monkeypatch) -> None:
    monkeypatch.setattr(script_engine, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(
        script_engine,
        "_fetch_research_context",
        lambda title, prompt, genre: "- Elon Musk: South African-born entrepreneur and engineer.",
    )
    monkeypatch.setattr(
        script_engine,
        "_fetch_current_events_context",
        lambda prompt, limit=5, force=False: "- Recent coverage: public reporting about Elon Musk.",
    )
    captured: dict[str, object] = {}

    def fake_llm(topic, duration_minutes, tone, **kwargs):
        captured.update(kwargs)
        return {
            "full_script": "Research-grounded documentary script.",
            "scenes": [{"id": 1, "text": "Scene 1\nIntent: factual\nNarration:\nVerified context.\nVisuals:\nArchive."}],
        }

    monkeypatch.setattr(script_engine, "_generate_script_llm", fake_llm)
    result = script_engine.generate_script(
        "A true story about Elon Musk",
        2,
        "documentary",
        genre="True Story",
    )
    assert result["scenes"]
    assert captured["factual_mode"] is True
    assert "Elon Musk" in str(captured["research_context"])
    assert "Recent coverage" in str(captured["current_events_context"])


def test_real_events_passes_research_context_to_xai(monkeypatch) -> None:
    monkeypatch.setattr(script_engine, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(
        script_engine,
        "_fetch_research_context",
        lambda title, prompt, genre: "- Apollo 11: the first crewed lunar landing mission.",
    )
    monkeypatch.setattr(
        script_engine,
        "_fetch_current_events_context",
        lambda prompt, limit=5, force=False: "- Recent coverage: archival event reporting.",
    )
    captured: dict[str, object] = {}

    def fake_llm(topic, duration_minutes, tone, **kwargs):
        captured.update(kwargs)
        return {
            "full_script": "Research-grounded real-events script.",
            "scenes": [{"id": 1, "text": "Scene 1\nIntent: factual\nNarration:\nApollo archive.\nVisuals:\nArchive."}],
        }

    monkeypatch.setattr(script_engine, "_generate_script_llm", fake_llm)
    result = script_engine.generate_script(
        "Archive of Apollo 11",
        2,
        "documentary",
        genre="Real Events",
    )
    assert result["scenes"]
    assert captured["factual_mode"] is True
    assert "Apollo 11" in str(captured["research_context"])
