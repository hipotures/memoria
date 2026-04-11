from __future__ import annotations

from memoria.vision.contracts import CandidateRef
from memoria.vision.contracts import EntityMention
from memoria.vision.contracts import VisionInterpretation
from memoria.vision.engines import VisionEngineResult
from memoria.vision.engines import extract_app_hint_from_filename

def map_vision_analysis_to_interpretation(
    *,
    analysis: VisionEngineResult,
    ocr_text: str,
    original_filename: str,
) -> VisionInterpretation:
    filename_app_hint = extract_app_hint_from_filename(original_filename).strip().lower() or None
    app_hint = (analysis.app_hint or filename_app_hint or "").strip().lower() or None
    semantic_summary = analysis.semantic_summary.strip() or ocr_text.strip() or "Generic screenshot."
    return VisionInterpretation(
        screen_category=(analysis.screen_category or "generic").strip().lower(),
        semantic_summary=semantic_summary,
        app_hint=app_hint,
        topic_candidates=[CandidateRef(**candidate) for candidate in analysis.topic_candidates],
        task_candidates=[CandidateRef(**candidate) for candidate in analysis.task_candidates],
        person_candidates=[CandidateRef(**candidate) for candidate in analysis.person_candidates],
        entity_mentions=[EntityMention(**mention) for mention in analysis.entity_mentions],
        searchable_labels=list(analysis.searchable_labels),
        cluster_hints=list(analysis.cluster_hints),
        confidence=dict(analysis.confidence),
        raw_model_payload=dict(analysis.raw_model_payload),
    )


def should_absorb_interpretation(interpretation: VisionInterpretation) -> bool:
    if interpretation.topic_candidates or interpretation.task_candidates or interpretation.person_candidates:
        return True
    if interpretation.entity_mentions or interpretation.searchable_labels or interpretation.cluster_hints:
        return True
    if interpretation.app_hint:
        return True
    return interpretation.screen_category not in {"", "generic"} and bool(
        interpretation.semantic_summary.strip()
    )
