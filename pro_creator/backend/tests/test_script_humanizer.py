from app.services.script_engine import (
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


def test_normalize_subject_title_strips_ad_wrappers() -> None:
    assert _normalize_subject_title("Pro Creator Launch Ad") == "Pro Creator"
    assert _normalize_subject_title("Promotional Ad for Pro Creator App") == "Pro Creator App"
