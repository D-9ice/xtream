from typing import Dict, List, Tuple
import math
import re
import json
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

from app.config import (
    PROVIDER_RETRY_ATTEMPTS,
    PROVIDER_RETRY_BACKOFF_SECONDS,
    XAI_API_KEY,
    XAI_BASE_URL,
    XAI_TEXT_MODEL,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _wants_current_events(prompt: str) -> bool:
    p = (prompt or "").lower()
    markers = (
        "current event",
        "current affairs",
        "latest",
        "recent",
        "today",
        "breaking",
        "live event",
        "headline",
        "news",
    )
    return any(m in p for m in markers)


def _fetch_current_events_context(prompt: str, limit: int = 5, force: bool = False) -> str:
    if not force and not _wants_current_events(prompt):
        return ""
    query = re.sub(r"\s+", " ", (prompt or "")).strip()[:120]
    if not query:
        return ""
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as exc:
        logger.warning("Current-events context fetch failed: %s", exc)
        return ""

    items: list[str] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        compact_title = re.sub(r"\s+", " ", title)
        if pub_date:
            items.append(f"- {compact_title} ({pub_date})")
        else:
            items.append(f"- {compact_title}")
        if len(items) >= limit:
            break
    return "\n".join(items)


def _fetch_wikipedia_context(query: str) -> str:
    clean_query = re.sub(r"\s+", " ", (query or "")).strip()
    if not clean_query:
        return ""

    try:
        search_response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": clean_query,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
            timeout=6,
        )
        search_response.raise_for_status()
        search_payload = search_response.json()
    except Exception as exc:
        logger.warning("Wikipedia search context fetch failed: %s", exc)
        return ""

    titles = search_payload[1] if isinstance(search_payload, list) and len(search_payload) > 1 else []
    snippets = search_payload[2] if isinstance(search_payload, list) and len(search_payload) > 2 else []
    title = titles[0] if titles else clean_query
    snippet = snippets[0] if snippets else ""

    try:
        summary_response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}",
            timeout=6,
        )
        if summary_response.ok:
            summary_payload = summary_response.json()
            summary = (summary_payload.get("extract") or "").strip()
            if summary:
                if snippet:
                    return f"- {title}: {summary}\n- Search summary: {snippet}"
                return f"- {title}: {summary}"
    except Exception as exc:
        logger.warning("Wikipedia summary context fetch failed: %s", exc)

    if snippet:
        return f"- {title}: {snippet}"
    return f"- {title}"


def _extract_research_subject(title: str, prompt: str) -> str:
    seed = " ".join(part for part in [title, prompt] if part).strip()
    if not seed:
        return "the subject"

    patterns = [
        r"(?i)\btrue story about\s+(.+?)(?:[.!?]|$)",
        r"(?i)\bstory about\s+(.+?)(?:[.!?]|$)",
        r"(?i)\babout\s+(.+?)(?:[.!?]|$)",
        r"(?i)\bof\s+(.+?)(?:[.!?]|$)",
        r"(?i)\bon\s+(.+?)(?:[.!?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, seed)
        if match:
            subject = match.group(1).strip(" -,:;")
            subject = re.sub(r"(?i)^(?:the|a|an)\s+", "", subject).strip()
            if subject:
                return subject

    cleaned = re.sub(r"(?i)\btrue story\b", " ", seed)
    cleaned = re.sub(r"(?i)\bstory\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\breal\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:;")
    return cleaned or "the subject"


def _is_true_story_genre(genre: str | None, prompt: str = "", title: str = "") -> bool:
    haystack = " ".join(part for part in [genre or "", prompt or "", title or ""] if part).lower()
    return "true story" in haystack or "real events" in haystack


def _fetch_research_context(title: str, prompt: str, genre: str | None) -> str:
    subject = _extract_research_subject(title, prompt)
    parts: list[str] = []
    wiki_context = _fetch_wikipedia_context(subject)
    if wiki_context:
        parts.append("Background research:\n" + wiki_context)
    news_context = _fetch_current_events_context(subject, limit=5, force=True)
    if news_context:
        parts.append("Recent coverage:\n" + news_context)
    if not parts and _is_true_story_genre(genre, prompt=prompt, title=title):
        parts.append(f"Use only verifiable facts about {subject}.")
    return "\n\n".join(parts)


def _strict_story_directives(
    *,
    title: str,
    prompt: str,
    tone: str,
    duration_minutes: float,
    genre: str | None,
    factual_mode: bool,
    scene_count: int,
) -> list[str]:
    duration_minutes_f = _normalize_duration_minutes(duration_minutes)
    duration_seconds = int(round(duration_minutes_f * 60))
    target_words = _estimate_target_word_count(duration_minutes_f)
    words_per_scene = max(20, int(round(target_words / max(1, scene_count))))
    genre_label = (genre or "").strip() or "Unspecified"
    directives = [
        "- Script coherence: bulletproof. No plot holes, contradictions, or scene drift.",
        "- Single-character DNA: keep each named character's identity, backstory, voice, mannerisms, and motivations identical in every line and scene.",
        "- Multi-character DNA: when multiple characters appear, keep each voice distinct and never merge traits, cadence, relationships, or emotional logic.",
        "- DNA inference rule: if no DNA is supplied, infer stable single- and multi-character DNA from the title, brief, genre, and scene logic, then keep it unchanged from scene to scene.",
        f"- Genre adherence: obey {genre_label} strictly; do not blend genres or drift tone.",
        "- Dialogue coherence: every spoken line must be logical and advance the scene.",
        "- Voice allocation: each dialogue line must clearly belong to the correct character.",
        f"- Duration adherence: pace the story for {duration_minutes_f:g} minutes (~{duration_seconds}s) across {scene_count} scenes.",
        f"- Word-count adherence: target about {words_per_scene} words per scene and stay within roughly ±10% of the total target word count.",
        "- Tone control: keep pacing, atmosphere, and emotional weight locked to the requested tone.",
    ]
    if factual_mode:
        directives.extend(
            [
                "- Factual integrity: use only verified details from the research context; do not invent unsupported facts, events, dialogue, motivations, or dates.",
                "- Documentary discipline: stay evidence-led, grounded, and precise.",
            ]
        )
    else:
        directives.extend(
            [
                "- Story momentum: every scene must escalate, reveal, or pay off something new.",
                "- Scene payoff: end each scene with a reason to keep watching.",
            ]
        )
    return directives


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
        f"Open hard: {title} turns {angle} into an immediate visual and emotional hit.",
        f"The bottleneck breaks the moment {title} takes over {angle} with precision.",
        f"One sharp move can flip the whole story, and {title} makes {angle} land fast.",
        f"Right away, {title} pushes {angle} into a cleaner, stronger, more cinematic flow.",
    ]
    development = [
        f"Keep the pressure on, anchor the story in {brief_focus}, and let every beat escalate the promise.",
        f"Drive forward with {angle} so the scene never loses grip or momentum.",
        "Every move should feel purposeful, high-contrast, and ready to cut straight into the next beat.",
        "The result is tighter pacing, sharper impact, and a stronger reason to keep watching.",
    ]
    credibility = [
        f"The tone stays {style_b}, with short, punchy lines built for confident voiceover delivery.",
        "No soft setup, no wandering, just a clean production path from opening hit to final payoff.",
        "Built for creators, marketers, and brands that need speed without losing edge or polish.",
        "Everything is shaped to move with intent, confidence, and cinematic momentum.",
    ]
    p1 = openers[(scene_index - 1) % len(openers)]
    p2 = development[(scene_index - 1) % len(development)]
    p3 = credibility[(scene_index - 1) % len(credibility)]
    if scene_index < scene_count:
        p4 = (
            f"Next, we cut into {next_angle} and keep the tension climbing into scene {scene_index + 1}."
        )
    else:
        p4 = (
            f"Now lock in {title}, finish with force, and publish your next standout video with confidence."
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
        f"Meet {subject}: the opening move that turns raw ideas into a sharper, faster result.",
        f"When the pace matters, {subject} keeps every part of the production chain locked together.",
        f"{subject} pulls concept, production, and delivery into one controlled run from the first beat.",
        f"If the workflow feels scattered, {subject} cuts through it and restores momentum.",
        f"{subject} gives creators and teams a single command line for end-to-end production.",
        f"Launch-ready output starts with {subject} and lands with platform-ready force.",
        f"With {subject}, quality can scale without the process losing shape or speed.",
        f"{subject} is built for faster delivery, cleaner output, and a stronger creative finish.",
    ]
    proofs = [
        "Generate a sharp script in minutes, then move it into narration with production-ready clarity.",
        "Create on-brand visuals instantly, sync scenes, and assemble a polished cut for every platform.",
        "Cut tool-switching, reduce production drag, and publish more campaigns with less friction.",
        "Stay in flow from first prompt to final export while the creative standard stays high.",
        "Move from idea to script, script to voice, voice to visuals, and visuals to final video in one run.",
        "Keep your brand voice consistent while reducing turnaround time and tightening the final cut.",
        "Go from rough concept to polished campaign asset with fewer handoffs and stronger control.",
        "Ship faster without sacrificing quality by running the whole creative pipeline inside one app.",
    ]
    opener = openers[(scene_index - 1) % len(openers)]
    proof = proofs[(scene_index - 1) % len(proofs)]
    cta = (
        f"Next, we hit {next_angle} to keep the pressure building."
        if scene_index < scene_count
        else f"Start creating with {subject} now and launch your next high-performing piece with force."
    )
    return "\n\n".join([opener, proof, cta])


def _compose_factual_narration(
    *,
    title: str,
    prompt: str,
    research_context: str,
    beat_title: str,
    beat_intent: str,
    angle: str,
    next_angle: str,
    scene_index: int,
    scene_count: int,
) -> str:
    research_lines = [
        line.strip(" -•")
        for line in (research_context or "").splitlines()
        if line.strip() and not line.lower().startswith(("background research:", "recent coverage:"))
    ]
    evidence = research_lines[(scene_index - 1) % len(research_lines)] if research_lines else ""
    subject = _extract_research_subject(title, prompt)
    opener = [
        f"This is a factual look at {subject}, told directly from the documented record.",
        f"We open with the verified story around {subject} and keep every detail grounded in evidence.",
        f"The narration stays rooted in what can be checked about {subject} and nothing else.",
        f"Scene by scene, we stay with the confirmed public record about {subject}.",
    ][(scene_index - 1) % 4]
    detail = (
        evidence
        if evidence
        else f"This section focuses on the documented {beat_title.lower()} within the larger story."
    )
    development = (
        f"The beat centers on {beat_intent.lower()} while staying faithful to the available research."
    )
    if scene_index < scene_count:
        bridge = (
            f"Next we move into {next_angle} without inventing unsupported details."
        )
    else:
        bridge = (
            f"That closes the verified arc and leaves the audience with a grounded take on {subject}."
        )
    return "\n\n".join([opener, detail, development, bridge])


def _estimate_target_word_count(duration_minutes: float) -> int:
    duration_minutes_f = _normalize_duration_minutes(duration_minutes)
    return max(80, int(round(duration_minutes_f * 145)))


def _build_script_blueprint(
    *,
    title: str,
    prompt: str,
    tone: str,
    duration_minutes: float,
    genre: str | None,
    factual_mode: bool,
    scene_count: int,
) -> list[str]:
    duration_minutes_f = _normalize_duration_minutes(duration_minutes)
    duration_seconds = int(round(duration_minutes_f * 60))
    target_words = _estimate_target_word_count(duration_minutes_f)
    words_per_scene = max(20, int(round(target_words / max(1, scene_count))))
    genre_label = (genre or "").strip() or "Unspecified"
    blueprint = [
        "Script Blueprint:",
        f"- Title: {title}",
        f"- Brief: {prompt}",
        f"- Tone: {tone}",
        f"- Selected genre: {genre_label}",
        f"- Target length: {duration_minutes_f:g} minutes (~{duration_seconds}s) / about {target_words} words.",
        *_strict_story_directives(
            title=title,
            prompt=prompt,
            tone=tone,
            duration_minutes=duration_minutes_f,
            genre=genre,
            factual_mode=factual_mode,
            scene_count=scene_count,
        ),
        "- Hook rule: open immediately with a vivid hook, conflict, reveal, or promise. No soft introductions.",
        "- Momentum rule: every scene must escalate, reveal, or pay off something new.",
        f"- Pacing rule: aim for about {words_per_scene} words per scene and stay within roughly ±10% of the target word count.",
        "- Structure rule: Hook -> Escalation -> Turn -> Payoff -> Transition.",
        "- Voice rule: write final narration, not notes to a writer.",
        "- Genre rule: every beat must unmistakably belong to the selected genre.",
        "- Intrigue rule: every scene must end with a reason to keep watching.",
    ]
    if factual_mode:
        blueprint.extend(
            [
                "- Factual rule: use only verified details from the research context; do not invent unsupported facts, events, or dialogue.",
                "- Documentary rule: keep the narration grounded, precise, and evidence-led.",
            ]
        )
    else:
        blueprint.extend(
            [
                "- Attention rule: make the opening punchy, specific, and emotionally active.",
                "- Payoff rule: land every scene with a memorable line or visual beat that advances the story.",
            ]
        )
    return blueprint


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


def _generate_script_template(
    topic: str,
    duration_minutes: float,
    tone: str,
    *,
    genre: str | None = None,
    current_events_context: str = "",
    research_context: str = "",
    factual_mode: bool = False,
) -> Dict:
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
    factual_mode = factual_mode or _is_true_story_genre(None, prompt=prompt, title=title)

    script_lines = [
        f"Title: {title}",
        f"Tone: {tone}",
        f"Duration: {duration_minutes_f:g} minutes (~{duration_seconds}s)",
        "",
        f"Brief: {prompt}",
        "",
        *_build_script_blueprint(
            title=title,
            prompt=prompt,
            tone=tone,
            duration_minutes=duration_minutes_f,
            genre=genre,
            factual_mode=factual_mode,
            scene_count=scene_count,
        ),
        (
            "Overview: A fact-driven narration plan grounded in research and public reporting."
            if factual_mode
            else "Overview: A human-sounding narration plan built for YouTube pacing, clarity, and trust."
        ),
        "",
    ]
    if current_events_context:
        script_lines.extend(
            [
                "Current Events Signals:",
                current_events_context,
                "",
            ]
        )
    if research_context:
        script_lines.extend(
            [
                "Research Context:",
                research_context,
                "",
            ]
        )

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
        elif factual_mode:
            narration = _compose_factual_narration(
                title=title,
                prompt=prompt,
                research_context=research_context or current_events_context,
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
    base_url: str = XAI_BASE_URL,
    api_key: str = "",
    genre: str | None = None,
    current_events_context: str = "",
    research_context: str = "",
    factual_mode: bool = False,
) -> Dict | None:
    api_key = api_key.strip()
    if not api_key:
        return None

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
    factual_mode = factual_mode or _is_true_story_genre(None, prompt=prompt, title=title)

    if factual_mode:
        system_prompt = (
            "You are a documentary script writer focused on factual, source-grounded narration. "
            "Use only the provided research context. Do not invent facts, events, dialogue, motivations, or dates. "
            "If the research context is incomplete, stay general and avoid unsupported specifics. "
            "Follow every strict story directive exactly and keep each beat aligned with the selected genre and target word count."
        )
    else:
        system_prompt = (
            "You are a senior YouTube script writer. "
            "Write natural, human-sounding narration with varied sentence rhythm. "
            "Use a strict hook -> escalation -> payoff structure. "
            "Preserve character DNA, obey the selected genre, and stay close to the target word count. "
            "Follow every strict story directive exactly. "
            "Avoid meta writing advice, avoid repetitive phrasing, and avoid template filler."
        )
    user_prompt_parts = [
        f"Title: {title}",
        f"Brief: {prompt}",
        f"Tone: {tone}",
        f"Duration minutes: {duration_minutes_f:g} (~{duration_seconds}s)",
        f"Selected genre: {(genre or '').strip() or 'Unspecified'}",
        f"Scene count: {scene_count}",
        "",
    ]
    if factual_mode:
        user_prompt_parts.append("Research mode: TRUE STORY / factual documentary")
    user_prompt_parts.extend(
        _build_script_blueprint(
            title=title,
            prompt=prompt,
            tone=tone,
            duration_minutes=duration_minutes_f,
            genre=genre,
            factual_mode=factual_mode,
            scene_count=scene_count,
        )
    )
    if research_context:
        user_prompt_parts.extend(
            [
                "",
                "Research context:",
                research_context,
                "",
            ]
        )
    user_prompt_parts.extend(
        [
            "Return strict JSON with this shape:",
            "{",
            '  "full_script": "string",',
            '  "scenes": [{"id": 1, "text": "string"}]',
            "}",
            "Rules:",
            "- Each scene text must contain: Scene title line, Intent line, Narration section, Visuals section.",
            "- Narration must read like final voiceover prose, not instructions to a writer.",
        ]
    )
    if factual_mode:
        user_prompt_parts.extend(
            [
                "- Use only verifiable claims from the research context; do not fictionalize or dramatize unsupported details.",
                "- Prefer documentary narration, archival framing, and evidence-based sequencing.",
            ]
        )
    user_prompt_parts.extend(
        [
            "- Keep scenes coherent and progressive from hook to call to action.",
            "- No repeated boilerplate sentences across scenes.",
        ]
    )
    user_prompt = "\n".join(user_prompt_parts)
    if current_events_context:
        user_prompt += (
            "\nCurrent events context (optional, use only if relevant to brief):\n"
            f"{current_events_context}\n"
            "- If used, reference events naturally without making unverifiable claims.\n"
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
    genre: str | None = None,
) -> Dict:
    selected_model = (model_name or XAI_TEXT_MODEL).strip()
    _title, brief_prompt = _parse_script_brief(topic)
    factual_mode = _is_true_story_genre(genre, prompt=brief_prompt, title=_title)
    current_events_context = _fetch_current_events_context(
        brief_prompt,
        force=factual_mode,
    )
    research_context = _fetch_research_context(_title, brief_prompt, genre) if factual_mode else ""
    if not XAI_API_KEY.strip():
        return _generate_script_template(
            topic,
            duration_minutes,
            tone,
            genre=genre,
            current_events_context=current_events_context,
            research_context=research_context,
            factual_mode=factual_mode,
        )
    llm_result = _generate_script_llm(
        topic,
        duration_minutes,
        tone,
        model_name=selected_model,
        api_key=XAI_API_KEY,
        base_url=XAI_BASE_URL,
        genre=genre,
        current_events_context=current_events_context,
        research_context=research_context,
        factual_mode=factual_mode,
    )
    if llm_result:
        return llm_result
    return _generate_script_template(
        topic,
        duration_minutes,
        tone,
        genre=genre,
        current_events_context=current_events_context,
        research_context=research_context,
        factual_mode=factual_mode,
    )
