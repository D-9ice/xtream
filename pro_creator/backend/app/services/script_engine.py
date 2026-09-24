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


def _normalize_duration_minutes(duration_minutes: float) -> float:
    try:
        minutes = float(duration_minutes)
    except Exception:
        minutes = 3.0
    if not math.isfinite(minutes):
        minutes = 3.0
    # We accept fractional minutes (ads). Clamp but keep the fractional value.
    return max(0.25, min(90.0, minutes))


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
                logger.warning("xAI script generation failed after retries: %s", exc)
                return None
            time.sleep(PROVIDER_RETRY_BACKOFF_SECONDS * attempt)
    return None


def generate_script(
    topic: str,
    duration_minutes: float,
    tone: str,
    *,
    genre: str | None = None,
) -> Dict:
    selected_model = XAI_TEXT_MODEL.strip()
    if not XAI_API_KEY.strip():
        raise RuntimeError("XAI_API_KEY is required for script generation")
    _title, brief_prompt = _parse_script_brief(topic)
    factual_mode = _is_true_story_genre(genre, prompt=brief_prompt, title=_title)
    current_events_context = _fetch_current_events_context(
        brief_prompt,
        force=factual_mode,
    )
    research_context = _fetch_research_context(_title, brief_prompt, genre) if factual_mode else ""
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
    raise RuntimeError("xAI script generation failed to return a valid script")
