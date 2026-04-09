from __future__ import annotations

import re

from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import VisionEngineResult
from memoria.vision.engines import extract_app_hint_from_filename

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEADING_SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9_-]*)\s*:")
_TRIP_LOCATION_RE = re.compile(
    r"\b(?:for|to)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)"
)
_TRAVEL_SIGNAL_RE = re.compile(r"\b(?:trip|travel|train|flight|hotel)\b")
_AMBIGUOUS_TRIP_LOCATION_TOKENS = {
    "finance",
    "monday",
    "reimbursement",
    "support",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}
_CHAT_APP_HINTS = {
    "discord",
    "messenger",
    "signal",
    "slack",
    "telegram",
    "whatsapp",
}
_CHAT_CATEGORY_KEYWORDS = {
    "chat",
    "comments",
    "conversation",
    "messaging",
}


def map_vision_analysis_to_interpretation(
    *,
    analysis: VisionEngineResult,
    ocr_text: str,
    original_filename: str,
) -> VisionInterpretation:
    lower_text = ocr_text.lower()
    has_travel_signal = _TRAVEL_SIGNAL_RE.search(lower_text) is not None
    topic_candidates: list[CandidateRef] = []
    task_candidates: list[CandidateRef] = []
    person_candidates: list[CandidateRef] = []

    trip_match = _TRIP_LOCATION_RE.search(ocr_text) if has_travel_signal else None
    if trip_match is not None:
        location_title = trip_match.group(1).strip()
        if _is_plausible_trip_location(location_title):
            topic_candidates.append(
                CandidateRef(
                    slug=f"trip-to-{_slugify(location_title)}",
                    title=f"Trip to {location_title}",
                    confidence=0.95,
                )
            )

    if "book train" in lower_text or "train ticket" in lower_text:
        task_candidates.append(
            CandidateRef(
                slug="book-train",
                title="Book train",
                confidence=0.89,
            )
        )

    speaker_match = _LEADING_SPEAKER_RE.match(ocr_text)
    if speaker_match is not None and (topic_candidates or task_candidates):
        person_title = speaker_match.group(1).strip()
        person_candidates.append(
            CandidateRef(
                slug=_slugify(person_title),
                title=person_title,
                confidence=0.62,
            )
        )

    filename_app_hint = extract_app_hint_from_filename(original_filename)
    app_hint = _normalize_app_hint(analysis.app_hint or filename_app_hint)
    has_chat_signal = _has_chat_signal(
        analysis=analysis,
        speaker_match=speaker_match is not None,
        has_candidates=bool(topic_candidates or task_candidates),
        app_hint=app_hint,
    )

    semantic_summary = analysis.summary_en or analysis.summary_pl or ocr_text
    return VisionInterpretation(
        screen_category="chat" if has_chat_signal else "generic",
        semantic_summary=semantic_summary,
        app_hint=app_hint,
        topic_candidates=topic_candidates,
        task_candidates=task_candidates,
        person_candidates=person_candidates,
        confidence={
            "screen_category": 0.80 if has_chat_signal else 0.35,
            "semantic_summary": 0.80 if (analysis.summary_en or analysis.summary_pl) else 0.55,
            "app_hint": 0.55 if app_hint else 0.0,
        },
    )


def should_absorb_interpretation(interpretation: VisionInterpretation) -> bool:
    return bool(interpretation.topic_candidates and interpretation.task_candidates)


def _normalize_app_hint(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    return stripped or None


def _has_chat_signal(
    *,
    analysis: VisionEngineResult,
    speaker_match: bool,
    has_candidates: bool,
    app_hint: str | None,
) -> bool:
    category_tokens = {
        label.en.strip().lower()
        for label in analysis.categories
        if label.en.strip()
    }
    if app_hint in _CHAT_APP_HINTS:
        return True
    if category_tokens.intersection(_CHAT_CATEGORY_KEYWORDS):
        return True
    return speaker_match and has_candidates


def _slugify(value: str) -> str:
    slug = _NON_ALNUM_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "unknown"


def _is_plausible_trip_location(location_title: str) -> bool:
    normalized_tokens = {token.lower() for token in location_title.strip().split()}
    return not normalized_tokens.intersection(_AMBIGUOUS_TRIP_LOCATION_TOKENS)
