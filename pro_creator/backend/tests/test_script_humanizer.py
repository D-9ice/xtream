import app.services.script_engine as script_engine

from app.services.script_engine import (
    _build_script_blueprint,
    _generate_script_template,
    _normalize_subject_title,
    _parse_script_brief,
)


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


def test_template_output_avoids_legacy_robotic_phrases() -> None:
    result = _generate_script_template(
        topic=(
            "Promotional Ad for Pro Creator App. "
            "Create a high-energy one-minute ad for creators and marketers."
        ),
        duration_minutes=1,
        tone="excited",
    )
    script = result["full_script"].lower()
    assert "start this beat by framing" not in script
    assert "end this section by bridging naturally" not in script
    assert "everyday drivers" not in script
    assert "publish-ready" in script


def test_template_promo_fallback_is_domain_agnostic() -> None:
    result = _generate_script_template(
        topic=(
            "Title: Launch Teaser for Pixel Brew Co "
            "Prompt: Write a one-minute promotional ad for a specialty coffee brand launching cold brew."
        ),
        duration_minutes=1,
        tone="excited",
    )
    script = result["full_script"]
    assert "Pro Creator" not in script
    assert "Pixel Brew Co" in script


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


def test_true_story_genre_uses_factual_research_context(monkeypatch) -> None:
    monkeypatch.setattr(script_engine, "XAI_API_KEY", "")
    monkeypatch.setattr(
        script_engine,
        "_fetch_wikipedia_context",
        lambda query: "- Elon Musk: South African-born entrepreneur and engineer.",
    )
    monkeypatch.setattr(
        script_engine,
        "_fetch_current_events_context",
        lambda prompt, limit=5, force=False: "- Recent coverage: public reporting about Elon Musk.",
    )

    result = script_engine.generate_script(
        "A true story about Elon Musk",
        2,
        "documentary",
        genre="True Story",
    )
    script = result["full_script"]

    assert "fact-driven narration" in script.lower()
    assert "Elon Musk" in script
    assert "Recent coverage" in script


def test_real_events_genre_uses_factual_research_context(monkeypatch) -> None:
    monkeypatch.setattr(script_engine, "XAI_API_KEY", "")
    monkeypatch.setattr(
        script_engine,
        "_fetch_wikipedia_context",
        lambda query: "- Apollo 11: the first crewed lunar landing mission.",
    )
    monkeypatch.setattr(
        script_engine,
        "_fetch_current_events_context",
        lambda prompt, limit=5, force=False: "- Recent coverage: archival event reporting.",
    )

    result = script_engine.generate_script(
        "Archive of Apollo 11",
        2,
        "documentary",
        genre="Real Events",
    )
    script = result["full_script"]

    assert "fact-driven narration" in script.lower()
    assert "Apollo 11" in script
    assert "Recent coverage" in script


def test_normalize_subject_title_strips_ad_wrappers() -> None:
    assert _normalize_subject_title("Pro Creator Launch Ad") == "Pro Creator"
    assert _normalize_subject_title("Promotional Ad for Pro Creator App") == "Pro Creator App"
