from typing import Dict, List, Tuple
import math
import re
import json
import os
import time

import requests

from app.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    SCRIPT_PROVIDER,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_script_brief(raw_topic: str) -> Tuple[str, str]:
    text = (raw_topic or "").strip()
    if not text:
        return ("Untitled Story", "a clear and useful story brief")

    inline = re.sub(r"\s+", " ", text)
    title_match = re.search(r"(?i)\btitle\b\s*:?\s*(.+?)(?=\bprompt\b\s*:?\s*|$)", inline)
    prompt_match = re.search(r"(?i)\bprompt\b\s*:?\s*(.+)$", inline)
    if title_match or prompt_match:
        title = (title_match.group(1).strip() if title_match else "").strip(" -,:;")
        prompt = (prompt_match.group(1).strip() if prompt_match else "").strip()
        if not prompt:
            prompt = title or inline
        if not title:
            title = re.sub(r"\s+", " ", prompt).strip()[:90].strip(" -,:;")
        return (title or "Untitled Story", prompt or "a clear and useful story brief")

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


def _is_promo_ad_prompt(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    promo_markers = [
        "promotional",
        "promotion",
        "advertisement",
        "ad script",
        "launch",
        "ultimate app",
        "call-to-action",
        "cta",
        "install",
    ]
    return any(marker in lowered for marker in promo_markers)


def _normalize_subject_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", (title or "")).strip(" -,:;")
    if not cleaned:
        return ""
    # Handle prefixes like "Promotional Ad for X".
    cleaned = re.sub(
        r"(?i)^(?:promotional|promotion|launch|marketing|campaign)?\s*ad(?:vertisement)?\s*(?:for)?\s+",
        "",
        cleaned,
    ).strip(" -,:;")
    # Handle suffixes like "X Launch Ad", "X Promo", "X Campaign".
    cleaned = re.sub(
        r"(?i)\s+(?:launch\s+ad|promotional\s+ad|promotion(?:al)?|campaign|advertisement|ad)$",
        "",
        cleaned,
    ).strip(" -,:;")
    return cleaned


def _infer_subject(title: str, prompt: str) -> str:
    title_clean = _normalize_subject_title(title)
    if title_clean and title_clean.lower() not in {"untitled story", "untitled"}:
        return title_clean

    prompt_clean = re.sub(r"\s+", " ", (prompt or "")).strip()
    if not prompt_clean:
        return "this project"

    # Prefer short noun-like fragments after explicit "for ...".
    m = re.search(r"(?i)\bfor\s+([a-z0-9][a-z0-9 '&+\\-/]{2,80})", prompt_clean)
    if m:
        candidate = m.group(1).strip(" .,:;")
        if candidate:
            return candidate[:80]
    return prompt_clean[:80].strip(" -,:;") or "this project"


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
        lowered = part.lower()
        if lowered.startswith(("write ", "create ", "include ", "structure ", "keep ", "use ")):
            continue
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
    if "creator" in prompt_l or "content" in prompt_l:
        mapped.append("creator productivity and workflow speed")
    if "marketing" in prompt_l or "brand" in prompt_l:
        mapped.append("campaign performance and brand consistency")
    if "script" in prompt_l:
        mapped.append("from idea to script in minutes")
    if "voice" in prompt_l or "narration" in prompt_l:
        mapped.append("studio-style narration without recording bottlenecks")
    if "image" in prompt_l or "visual" in prompt_l:
        mapped.append("on-brand visuals generated on demand")
    if "video" in prompt_l or "export" in prompt_l:
        mapped.append("final video output ready for every channel")
    if "cost" in prompt_l or "price" in prompt_l or "value" in prompt_l:
        mapped.append("production cost efficiency at scale")

    base = [chunk for chunk in _phrase_chunks(prompt, limit=6) if not chunk.lower().startswith("write ")]
    defaults = [
        "clear value proposition in the first five seconds",
        "from idea to publish-ready output in one workflow",
        "consistent quality across short-form and long-form formats",
        "faster turnaround with fewer production bottlenecks",
        "audience retention through stronger hooks and pacing",
        "brand consistency across campaigns and channels",
        "lower production friction for solo creators and teams",
        "conversion-focused call-to-action that feels natural",
        "content velocity without sacrificing polish",
        "repeatable workflow for reliable publishing cadence",
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
    brief_focus = " ".join(prompt.split()[:20]).strip()
    openers = [
        f"Creators are moving fast, and {title} is built for exactly that speed.",
        f"If your content pipeline is slowing you down, {title} fixes the bottleneck at {angle}.",
        f"Imagine launching your next campaign with {angle} handled in one flow.",
        f"This is where {title} turns {angle} into publish-ready output.",
    ]
    development = [
        f"Start with a clear message, shape it fast, and keep the story anchored in {brief_focus}.",
        f"Then move from concept to execution with {angle} and no handoff friction.",
        "Every step keeps quality high while reducing the time between idea and publish.",
        "The result is cleaner output, faster iteration, and stronger performance per release.",
    ]
    credibility = [
        f"The tone stays {style_b}, with short, punchy lines that are ready for voiceover.",
        "No bloated workflow, no tool-hopping, just one production path from start to finish.",
        "Built for creators, marketers, and brands who need speed without sacrificing polish.",
        "Everything is designed to ship content consistently and confidently.",
    ]
    p1 = openers[(scene_index - 1) % len(openers)]
    p2 = development[(scene_index - 1) % len(development)]
    p3 = credibility[(scene_index - 1) % len(credibility)]
    if scene_index < scene_count:
        p4 = (
            f"Next, we move into {next_angle} to keep momentum into scene {scene_index + 1}."
        )
    else:
        p4 = (
            f"Now launch faster with {title}. Install Pro Creator and publish your next standout video today."
        )
    return "\n\n".join([p1, p2, p3, p4])


def _compose_promo_narration(
    *,
    title: str,
    prompt: str,
    angle: str,
    next_angle: str,
    scene_index: int,
    scene_count: int,
) -> str:
    subject = _infer_subject(title, prompt)
    openers = [
        f"Meet {subject}, built to turn raw ideas into publish-ready content fast.",
        f"When creators need speed and consistency, {subject} keeps each production step in sync.",
        f"{subject} brings concept, production, and delivery into one clean workflow.",
        f"If your content process feels fragmented, {subject} brings it together quickly.",
        f"{subject} gives creators and teams a single control center for end-to-end production.",
        f"Launch-ready output starts with {subject} and ends with platform-ready assets.",
        f"With {subject}, teams can scale quality output without scaling workflow chaos.",
        f"{subject} is built for faster delivery, cleaner output, and stronger creative control.",
    ]
    proofs = [
        "Generate a sharp script in minutes, then convert it to narration with production-ready voice.",
        "Create on-brand visuals instantly, sync scenes, and assemble polished edits for every platform.",
        "Cut tool-switching, reduce production overhead, and publish more campaigns with less effort.",
        "Stay in flow from first prompt to final export while keeping your creative standard high.",
        "Move from idea to script, script to voice, voice to visuals, and visuals to final video in one flow.",
        "Keep your brand voice consistent across content formats while reducing production turnaround time.",
        "Go from rough concept to polished campaign asset with fewer handoffs and better output control.",
        "Ship faster without sacrificing quality by running your creative pipeline end-to-end in one app.",
    ]
    opener = openers[(scene_index - 1) % len(openers)]
    proof = proofs[(scene_index - 1) % len(proofs)]
    cta = (
        f"Next, we push into {next_angle} to keep momentum."
        if scene_index < scene_count
        else f"Start creating with {subject} now and launch your next high-performing piece today."
    )
    return "\n\n".join([opener, proof, cta])


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


def _normalize_duration_minutes(duration_minutes: float) -> float:
    try:
        minutes = float(duration_minutes)
    except Exception:
        minutes = 3.0
    if not math.isfinite(minutes):
        minutes = 3.0
    # We accept fractional minutes (ads). Clamp but keep the fractional value.
    return max(0.25, min(90.0, minutes))


def _generate_script_template(topic: str, duration_minutes: float, tone: str) -> Dict:
    duration_minutes_f = _normalize_duration_minutes(duration_minutes)
    duration_seconds = int(round(duration_minutes_f * 60))
    if duration_seconds <= 20:
        scene_count = 4
    elif duration_seconds <= 35:
        scene_count = 5
    elif duration_seconds <= 60:
        scene_count = 6
    else:
        scene_count = max(6, min(10, math.ceil(duration_minutes_f / 5)))

    title, prompt = _parse_script_brief(topic)
    style_a, style_b = _tone_pack(tone)
    angles = _build_angles(prompt)
    plan = _scene_plan(scene_count)
    promo_mode = _is_promo_ad_prompt(prompt)

    script_lines = [
        f"Title: {title}",
        f"Tone: {tone}",
        f"Duration: {duration_minutes_f:g} minutes (~{duration_seconds}s)",
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
        if promo_mode:
            narration = _compose_promo_narration(
                title=title,
                prompt=prompt,
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


def _is_low_quality_script(full_script: str, scenes: List[Dict[str, str]]) -> bool:
    lowered = full_script.lower()
    banned_phrases = [
        "start this beat by framing",
        "end this section by bridging naturally",
        "keep the narration plain-spoken and credible",
        "everyday drivers",
    ]
    if any(phrase in lowered for phrase in banned_phrases):
        return True
    if not scenes:
        return True
    avg_scene_len = sum(len(scene.get("text", "")) for scene in scenes) / len(scenes)
    return avg_scene_len < 120


def _generate_script_llm(
    topic: str,
    duration_minutes: float,
    tone: str,
    *,
    model_name: str,
) -> Dict | None:
    api_key = OPENAI_API_KEY.strip()
    if not api_key:
        return None

    base_url = OPENAI_BASE_URL
    model = model_name.strip()
    duration_minutes_f = _normalize_duration_minutes(duration_minutes)
    duration_seconds = int(round(duration_minutes_f * 60))
    if duration_seconds <= 20:
        scene_count = 4
    elif duration_seconds <= 35:
        scene_count = 5
    elif duration_seconds <= 60:
        scene_count = 6
    else:
        scene_count = max(6, min(10, math.ceil(duration_minutes_f / 5)))
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
        f"Duration minutes: {duration_minutes_f:g} (~{duration_seconds}s)\n"
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

    def _run_once() -> Dict | None:
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
        if _is_low_quality_script(full_script, normalized_scenes):
            return None
        return {"full_script": full_script.strip(), "scenes": normalized_scenes}

    attempts = max(1, PROVIDER_RETRY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            result = _run_once()
            if result:
                logger.info("Generated script via LLM for title: %s", title)
            return result
        except Exception as exc:
            if attempt == attempts:
                logger.warning("LLM script generation failed, falling back to template: %s", exc)
                return None
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    return None


def generate_script(
    topic: str,
    duration_minutes: float,
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
            raise RuntimeError(
                "SCRIPT_PROVIDER=openai but LLM generation failed. "
                "Check OPENAI_API_KEY / OPENAI_BASE_URL / model configuration."
            )
    return _generate_script_template(topic, duration_minutes, tone)
