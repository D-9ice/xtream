from app.services.script_engine import _generate_script_template, _parse_script_brief


def test_parse_script_brief_supports_inline_title_prompt() -> None:
    raw = (
        "Title: Promotional Ad for Pro Creator App "
        "Prompt: Create a one-minute ad for Pro Creator that covers script, voice, image, and video."
    )
    title, prompt = _parse_script_brief(raw)
    assert title == "Promotional Ad for Pro Creator App"
    assert "one-minute ad for Pro Creator" in prompt


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
