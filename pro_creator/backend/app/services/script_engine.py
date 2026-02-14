from typing import Dict, List, Tuple
import math
import re
import json
import os

import requests

from app.config import OPENAI_BASE_URL, SCRIPT_PROVIDER
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_script_brief(raw_topic: str) -> Tuple[str, str]:
    text = (raw_topic or "").strip()
    if not text:
        return ("Untitled Story", "a clear and useful story brief")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = ""
    prompt_lines: List[str] = []

    for line in lines:
        lowered = line.lower()
        if lowered.startswith("title:"):
            title = line.split(":", 1)[1].strip()
            continue
        if lowered.startswith("prompt:"):
            prompt_lines.append(line.split(":", 1)[1].strip())
            continue
        prompt_lines.append(line)

    prompt = " ".join(part for part in prompt_lines if part).strip()
    if not title:
        title = re.sub(r"\s+", " ", (prompt or text)).strip()[:90].strip(" -,:;")
    if not prompt:
        prompt = title
    return (title or "Untitled Story", prompt or "a clear and useful story brief")


def _phrase_chunks(prompt: str, limit: int = 8) -> List[str]:
    raw_parts = re.split(r"[,\n;]+", prompt)
    parts = []
    for part in raw_parts:
        clean = re.sub(r"\s+", " ", part).strip(" .")
        if len(clean) < 6:
            continue
        parts.append(clean)
    unique: List[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
        if len(unique) >= limit:
            break
    return unique


def _build_angles(prompt: str) -> List[str]:
    prompt_l = prompt.lower()
    mapped: List[str] = []
    if "safety" in prompt_l:
        mapped.append("real-world safety outcomes")
    if "comfort" in prompt_l or "cabin" in prompt_l:
        mapped.append("daily comfort and cabin usability")
    if "design" in prompt_l or "aesthetic" in prompt_l:
        mapped.append("design choices that affect daily life")
    if "fsd" in prompt_l or "autopilot" in prompt_l or "driver-assist" in prompt_l:
        mapped.append("driver-assist expectations versus reality")
    if "ota" in prompt_l or "update" in prompt_l or "software" in prompt_l:
        mapped.append("software updates and long-term improvements")
    if "charging" in prompt_l or "range" in prompt_l:
        mapped.append("charging behavior and trip planning")
    if "cost" in prompt_l or "price" in prompt_l or "value" in prompt_l:
        mapped.append("ownership cost over time")

    base = [chunk for chunk in _phrase_chunks(prompt, limit=6) if not chunk.lower().startswith("write ")]
    defaults = [
        "real-world safety outcomes",
        "daily comfort and cabin usability",
        "software updates and long-term improvements",
        "charging behavior and trip planning",
        "performance when it actually matters",
        "ownership cost over time",
        "design choices that affect daily life",
        "driver-assist expectations versus reality",
        "resale and ecosystem value",
        "trade-offs every buyer should know",
    ]
    angles = mapped + base + defaults
    deduped: List[str] = []
    seen: set[str] = set()
    for angle in angles:
        key = angle.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(angle)
    return deduped


def _tone_pack(tone: str) -> Tuple[str, str]:
    t = tone.lower()
    if "professional" in t:
        return ("clear, confident", "measured and practical")
    if "energetic" in t:
        return ("fast, vivid", "high-momentum but grounded")
    if "calm" in t:
        return ("steady, thoughtful", "composed and reassuring")
    return ("natural, conversational", "plain-spoken and credible")


def _scene_plan(scene_count: int) -> List[Tuple[str, str]]:
    core = [
        ("Hook", "Open with the promise and the real-world question."),
        ("Problem", "Name the pain points and buyer doubts."),
        ("Promise", "Show what changes when the product delivers."),
        ("Blueprint", "Break down how the value appears in daily life."),
        ("Deep dive", "Go deeper into practical details and examples."),
        ("Proof", "Bring in evidence, comparisons, and constraints."),
        ("Recap", "Reinforce the strongest takeaways."),
        ("Call to action", "Close with a realistic next step."),
    ]
    if scene_count <= len(core):
        return core[:scene_count]

    filler = [
        ("Ownership lens", "Examine ownership from a different practical angle."),
        ("Use-case spotlight", "Focus on one audience segment and their priorities."),
        ("Myth check", "Address common objections and separate fact from hype."),
        ("Decision framework", "Help viewers compare choices with a clear rubric."),
    ]
    plan = core[:6]
    remaining = scene_count - 8
    for idx in range(remaining):
        plan.append(filler[idx % len(filler)])
    plan.extend(core[6:])
    return plan


def _compose_narration(
    *,
    title: str,
    prompt: str,
    tone: str,
    style_a: str,
    style_b: str,
    beat_title: str,
    beat_intent: str,
    angle: str,
    next_angle: str,
    scene_index: int,
    scene_count: int,
) -> str:
    intent_clean = beat_intent.rstrip(". ")
    brief_focus = " ".join(prompt.split()[:20]).strip()
    openers = [
        f"Start this beat by framing {title} around {angle}, then immediately show why it matters to everyday drivers.",
        f"Open with a concrete ownership moment tied to {angle}, so the audience feels the stakes before the explanation begins.",
        f"Lead with the central claim on {angle}, then test it with practical context instead of marketing language.",
        f"Introduce {angle} as a real decision point, not a feature list, and keep the delivery {style_a}.",
    ]
    development = [
        f"Build the section with one clear example, one measurable signal, and one honest limitation. Keep the perspective anchored in: {brief_focus}.",
        "Move from first-impression excitement to long-term ownership reality, and explain where expectations should be adjusted.",
        "Translate technical points into plain outcomes: confidence, convenience, cost, and stress level over time.",
        "Use contrast: what sounds great on paper versus what still holds up months later in daily use.",
    ]
    credibility = [
        f"Keep the narration {style_b}: short transitions, specific verbs, and no absolute claims.",
        "Ask one skeptical question on behalf of the viewer, answer it directly, and show the trade-off clearly.",
        "Treat the audience as informed buyers by showing both upside and friction in the same breath.",
        "Close each claim with a practical implication viewers can use in their own buying decision.",
    ]
    p1 = openers[(scene_index - 1) % len(openers)]
    p2 = development[(scene_index - 1) % len(development)]
    p3 = credibility[(scene_index - 1) % len(credibility)]
    if scene_index < scene_count:
        p4 = (
            f"End this section by bridging naturally into {next_angle}, setting up scene {scene_index + 1} with momentum."
        )
    else:
        p4 = "Finish with a grounded takeaway and a specific next action viewers can evaluate today."
    return "\n\n".join([p1, p2, p3, p4])


def _compose_visuals(beat_title: str, angle: str, scene_index: int) -> str:
    shot = [
        "Begin with a tangible action shot before any talking-head explanation.",
        "Pair close detail with wider context to keep clarity and momentum.",
        "Use overlays sparingly and only when they improve understanding.",
        "Include one reaction or lived moment to humanize the technical point.",
    ][(scene_index - 1) % 4]
    pacing = [
        "Alternate quick beats with short pauses to prevent monotony.",
        "Give each major claim one visual proof before moving on.",
        "Use b-roll to bridge dense ideas and keep narration breathable.",
        "Finish on a visual that previews the next narrative move.",
    ][(scene_index - 1) % 4]
    return (
        f"- Scene focus: {beat_title} framed around {angle}.\n"
        f"- {shot}\n"
        f"- {pacing}\n"
        "- Keep color, typography, and motion consistent with the segment's emotional intent."
    )


def _generate_script_template(topic: str, duration_minutes: int, tone: str) -> Dict:
    duration_minutes = max(1, min(45, duration_minutes))
    scene_count = max(6, min(10, math.ceil(duration_minutes / 5)))

    title, prompt = _parse_script_brief(topic)
    style_a, style_b = _tone_pack(tone)
    angles = _build_angles(prompt)
    plan = _scene_plan(scene_count)

    script_lines = [
        f"Title: {title}",
        f"Tone: {tone}",
        f"Duration: {duration_minutes} minutes",
        "",
        f"Brief: {prompt}",
        "Overview: A human-sounding narration plan built for YouTube pacing, clarity, and trust.",
        "",
    ]

    scenes: List[Dict[str, str]] = []
    for idx, (beat_title, beat_intent) in enumerate(plan, start=1):
        angle = angles[(idx - 1) % len(angles)]
        next_angle = angles[idx % len(angles)]
        narration = _compose_narration(
            title=title,
            prompt=prompt,
            tone=tone,
            style_a=style_a,
            style_b=style_b,
            beat_title=beat_title,
            beat_intent=beat_intent,
            angle=angle,
            next_angle=next_angle,
            scene_index=idx,
            scene_count=scene_count,
        )

        visuals = _compose_visuals(beat_title, angle, idx)
        scene_text = (
            f"Scene {idx}: {beat_title}\n"
            f"Intent: {beat_intent}\n"
            f"Narration:\n{narration}\n"
            f"Visuals:\n{visuals}"
        )
        scenes.append({"id": idx, "text": scene_text})
        script_lines.append(scene_text)
        script_lines.append("")

    full_script = "\n".join(script_lines).strip()
    logger.info("Generated script for title: %s", title)
    return {"full_script": full_script, "scenes": scenes}


def _extract_json_object(text: str) -> Dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    candidate = match.group(0) if match else cleaned
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _generate_script_llm(
    topic: str,
    duration_minutes: int,
    tone: str,
    *,
    model_name: str,
) -> Dict | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    base_url = OPENAI_BASE_URL
    model = model_name.strip()
    scene_count = max(6, min(10, math.ceil(duration_minutes / 5)))
    title, prompt = _parse_script_brief(topic)

    system_prompt = (
        "You are a senior YouTube script writer. "
        "Write natural, human-sounding narration with varied sentence rhythm. "
        "Avoid meta writing advice, avoid repetitive phrasing, and avoid template filler."
    )
    user_prompt = (
        f"Title: {title}\n"
        f"Brief: {prompt}\n"
        f"Tone: {tone}\n"
        f"Duration minutes: {duration_minutes}\n"
        f"Scene count: {scene_count}\n\n"
        "Return strict JSON with this shape:\n"
        "{\n"
        '  "full_script": "string",\n'
        '  "scenes": [{"id": 1, "text": "string"}]\n'
        "}\n"
        "Rules:\n"
        "- Each scene text must contain: Scene title line, Intent line, Narration section, Visuals section.\n"
        "- Narration must read like final voiceover prose, not instructions to a writer.\n"
        "- Keep scenes coherent and progressive from hook to call to action.\n"
        "- No repeated boilerplate sentences across scenes.\n"
    )

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.85,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json_object(content)
        if not parsed:
            return None
        full_script = parsed.get("full_script")
        scenes = parsed.get("scenes")
        if not isinstance(full_script, str) or not isinstance(scenes, list):
            return None
        normalized_scenes: List[Dict[str, str]] = []
        for idx, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            text = scene.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            scene_id = scene.get("id")
            if not isinstance(scene_id, int):
                scene_id = idx
            normalized_scenes.append({"id": scene_id, "text": text.strip()})
        if not normalized_scenes:
            return None
        logger.info("Generated script via LLM for title: %s", title)
        return {"full_script": full_script.strip(), "scenes": normalized_scenes}
    except Exception as exc:
        logger.warning("LLM script generation failed, falling back to template: %s", exc)
        return None


def generate_script(
    topic: str,
    duration_minutes: int,
    tone: str,
    *,
    script_provider: str | None = None,
    model_name: str | None = None,
) -> Dict:
    provider = (script_provider or SCRIPT_PROVIDER or "auto").lower()
    selected_model = (model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
    if provider in {"auto", "openai"}:
        llm_result = _generate_script_llm(
            topic,
            duration_minutes,
            tone,
            model_name=selected_model,
        )
        if llm_result:
            return llm_result
        if provider == "openai":
            logger.warning("OpenAI provider selected but unavailable, falling back to template")
    return _generate_script_template(topic, duration_minutes, tone)
