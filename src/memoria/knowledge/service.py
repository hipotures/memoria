from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import StageResult
from memoria.pipeline import record_stage_result

_OPEN_TASK_STATUS_PATTERNS = (
    re.compile(r"\bnot\s+done\b"),
    re.compile(r"\bnot\s+completed\b"),
    re.compile(r"\bnot\s+shipped\b"),
    re.compile(r"\bunfinished\b"),
    re.compile(r"\bunshipped\b"),
    re.compile(r"\bstill\s+open\b"),
    re.compile(r"\bpending\b"),
    re.compile(r"\bnot\s+ready\b"),
)
_DONE_TASK_STATUS_PATTERNS = (
    re.compile(r"\bdone\b"),
    re.compile(r"\bcompleted\b"),
    re.compile(r"\bshipped\b"),
)


@dataclass(frozen=True, slots=True)
class _CandidateSignal:
    slug: str
    title: str
    confidence: float


def absorb_interpreted_screenshot(
    session: Session,
    *,
    pipeline_run_id: int,
    source_item_id: int,
) -> list[str]:
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    if pipeline_run is None or pipeline_run.source_item_id != source_item_id:
        raise ValueError("pipeline_run_id does not belong to source_item_id")

    interpretation = session.get(AssetInterpretation, source_item_id)
    if interpretation is None:
        raise ValueError("asset_interpretation is required before absorb")

    source_item = session.get(SourceItem, source_item_id)
    assert source_item is not None

    observed_at = source_item.source_observed_at or source_item.source_created_at or _utc_now()
    topic_candidate = _highest_confidence_candidate(
        _load_candidates(interpretation.topic_candidates_json)
    )
    task_candidate = _highest_confidence_candidate(
        _load_candidates(interpretation.task_candidates_json)
    )
    person_candidate = _highest_confidence_candidate(
        _load_candidates(interpretation.person_candidates_json)
    )

    topic_token = topic_candidate.slug if topic_candidate is not None else f"source-item-{source_item_id}"
    topic_ref = f"topic:{topic_token}"
    topic_title = (
        topic_candidate.title if topic_candidate is not None else f"Source item {source_item_id}"
    )
    topic_confidence = topic_candidate.confidence if topic_candidate is not None else 0.0

    app_token = interpretation.app_hint or "generic"
    thread_ref = f"thread:{app_token}-{topic_candidate.slug if topic_candidate is not None else source_item_id}"
    thread_title = (
        f"{app_token} / {topic_title}"
        if topic_candidate is not None
        else f"{app_token} / Source item {source_item_id}"
    )
    thread_confidence = topic_confidence

    touched_refs = [
        _upsert_object(
            session,
            object_type="thread",
            object_ref=thread_ref,
            title=thread_title,
            confidence_score=thread_confidence,
        ),
        _upsert_object(
            session,
            object_type="topic",
            object_ref=topic_ref,
            title=topic_title,
            confidence_score=topic_confidence,
        ),
    ]

    _upsert_claim(
        session,
        claim_type="membership",
        subject_ref=thread_ref,
        predicate="belongs_to_topic",
        object_ref_or_value=topic_ref,
        observed_at=observed_at,
        confidence_score=topic_confidence,
        source_item_id=source_item_id,
    )

    if task_candidate is not None:
        task_ref = _upsert_object(
            session,
            object_type="task",
            object_ref=f"task:{task_candidate.slug}",
            title=task_candidate.title,
            confidence_score=task_candidate.confidence,
        )
        touched_refs.append(task_ref)
        _upsert_claim(
            session,
            claim_type="task_status",
            subject_ref=task_ref,
            predicate="status",
            object_ref_or_value=_infer_task_status(interpretation.semantic_summary),
            observed_at=observed_at,
            confidence_score=task_candidate.confidence,
            source_item_id=source_item_id,
        )

    if person_candidate is not None and person_candidate.confidence >= 0.60:
        person_ref = _upsert_object(
            session,
            object_type="person",
            object_ref=f"person:{person_candidate.slug}",
            title=person_candidate.title,
            confidence_score=person_candidate.confidence,
        )
        touched_refs.append(person_ref)
        _upsert_claim(
            session,
            claim_type="person_hint",
            subject_ref=thread_ref,
            predicate="involves_person",
            object_ref_or_value=person_ref,
            observed_at=observed_at,
            confidence_score=person_candidate.confidence,
            source_item_id=source_item_id,
        )

    session.flush()

    next_attempt = session.scalar(
        select(func.coalesce(func.max(StageResult.attempt), 0) + 1).where(
            StageResult.pipeline_run_id == pipeline_run_id,
            StageResult.stage_name == "absorb",
        )
    )
    assert next_attempt is not None

    record_stage_result(
        session,
        pipeline_run_id=pipeline_run_id,
        stage_name="absorb",
        status="completed",
        output_payload={"touched_refs": touched_refs},
        attempt=next_attempt,
    )
    return touched_refs


def _load_candidates(payload: str) -> list[_CandidateSignal]:
    return [
        _CandidateSignal(
            slug=str(candidate["slug"]),
            title=str(candidate["title"]),
            confidence=float(candidate["confidence"]),
        )
        for candidate in json.loads(payload)
    ]


def _highest_confidence_candidate(
    candidates: list[_CandidateSignal],
) -> _CandidateSignal | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: (-candidate.confidence, candidate.slug))[0]


def _upsert_object(
    session: Session,
    *,
    object_type: str,
    object_ref: str,
    title: str,
    confidence_score: float,
) -> str:
    knowledge_object = session.scalar(
        select(KnowledgeObject).where(KnowledgeObject.slug == object_ref)
    )
    if knowledge_object is None:
        knowledge_object = KnowledgeObject(
            object_type=object_type,
            slug=object_ref,
            title=title,
            status="active",
            confidence_score=confidence_score,
        )
        session.add(knowledge_object)
        return object_ref

    knowledge_object.object_type = object_type
    knowledge_object.title = title
    knowledge_object.status = "active"
    knowledge_object.confidence_score = confidence_score
    knowledge_object.last_confirmed_at = _utc_now()
    session.add(knowledge_object)
    return object_ref


def _upsert_claim(
    session: Session,
    *,
    claim_type: str,
    subject_ref: str,
    predicate: str,
    object_ref_or_value: str,
    observed_at: datetime,
    confidence_score: float,
    source_item_id: int,
) -> None:
    claim = _resolve_claim_for_upsert(
        session,
        claim_type=claim_type,
        subject_ref=subject_ref,
        predicate=predicate,
        object_ref_or_value=object_ref_or_value,
        observed_at=observed_at,
        confidence_score=confidence_score,
    )
    if claim is None:
        claim = KnowledgeClaim(
            claim_type=claim_type,
            subject_ref=subject_ref,
            predicate=predicate,
            object_ref_or_value=object_ref_or_value,
            observed_at=observed_at,
            status="active",
            confidence_score=confidence_score,
            evidence_set_id=f"{source_item_id}:{claim_type}:{predicate}",
        )
        session.add(claim)
        session.flush()
    else:
        claim.observed_at = observed_at
        if claim.object_ref_or_value == "uncertain" or claim.status == "uncertain":
            claim.status = "uncertain"
        else:
            claim.status = "active"
        claim.confidence_score = confidence_score
        claim.last_confirmed_at = _utc_now()
        session.add(claim)
        session.flush()

    _attach_evidence_once(session, claim_id=claim.id, source_item_id=source_item_id)


def _resolve_claim_for_upsert(
    session: Session,
    *,
    claim_type: str,
    subject_ref: str,
    predicate: str,
    object_ref_or_value: str,
    observed_at: datetime,
    confidence_score: float,
) -> KnowledgeClaim | None:
    if claim_type != "task_status":
        return session.scalar(
            select(KnowledgeClaim).where(
                KnowledgeClaim.claim_type == claim_type,
                KnowledgeClaim.subject_ref == subject_ref,
                KnowledgeClaim.predicate == predicate,
                KnowledgeClaim.object_ref_or_value == object_ref_or_value,
            )
        )

    task_claims = session.scalars(
        select(KnowledgeClaim)
        .where(
            KnowledgeClaim.claim_type == "task_status",
            KnowledgeClaim.subject_ref == subject_ref,
            KnowledgeClaim.predicate == predicate,
        )
        .order_by(KnowledgeClaim.id.asc())
    ).all()
    if not task_claims:
        return None

    exact_claim = next(
        (
            claim
            for claim in task_claims
            if claim.object_ref_or_value == object_ref_or_value and claim.status == "active"
        ),
        None,
    )
    uncertain_claim = next(
        (
            claim
            for claim in task_claims
            if claim.status == "uncertain" or claim.object_ref_or_value == "uncertain"
        ),
        None,
    )
    conflicting_claims = [
        claim for claim in task_claims if claim.object_ref_or_value != object_ref_or_value
    ]
    if conflicting_claims:
        canonical_claim = uncertain_claim or exact_claim or task_claims[0]
        _collapse_task_status_claims_to_uncertain(
            session,
            canonical_claim=canonical_claim,
            task_claims=task_claims,
            observed_at=observed_at,
            confidence_score=confidence_score,
        )
        return canonical_claim

    return exact_claim


def _collapse_task_status_claims_to_uncertain(
    session: Session,
    *,
    canonical_claim: KnowledgeClaim,
    task_claims: list[KnowledgeClaim],
    observed_at: datetime,
    confidence_score: float,
) -> None:
    canonical_claim.object_ref_or_value = "uncertain"
    canonical_claim.observed_at = observed_at
    canonical_claim.status = "uncertain"
    canonical_claim.confidence_score = confidence_score
    canonical_claim.last_confirmed_at = _utc_now()
    session.add(canonical_claim)
    session.flush()

    for task_claim in task_claims:
        if task_claim.id == canonical_claim.id:
            continue
        _move_evidence_links(session, from_claim_id=task_claim.id, to_claim_id=canonical_claim.id)
        session.delete(task_claim)

    session.flush()


def _move_evidence_links(
    session: Session,
    *,
    from_claim_id: int,
    to_claim_id: int,
) -> None:
    evidence_links = session.scalars(
        select(KnowledgeEvidenceLink)
        .where(KnowledgeEvidenceLink.claim_id == from_claim_id)
        .order_by(KnowledgeEvidenceLink.id.asc())
    ).all()
    existing_identities = {
        (
            link.source_item_id,
            link.fragment_type,
            link.fragment_ref,
        )
        for link in session.scalars(
            select(KnowledgeEvidenceLink).where(KnowledgeEvidenceLink.claim_id == to_claim_id)
        ).all()
    }

    for evidence_link in evidence_links:
        identity = (
            evidence_link.source_item_id,
            evidence_link.fragment_type,
            evidence_link.fragment_ref,
        )
        if identity in existing_identities:
            session.delete(evidence_link)
            continue

        evidence_link.claim_id = to_claim_id
        session.add(evidence_link)
        existing_identities.add(identity)


def _attach_evidence_once(
    session: Session,
    *,
    claim_id: int,
    source_item_id: int,
) -> None:
    evidence_link = session.scalar(
        select(KnowledgeEvidenceLink).where(
            KnowledgeEvidenceLink.claim_id == claim_id,
            KnowledgeEvidenceLink.source_item_id == source_item_id,
            KnowledgeEvidenceLink.fragment_type == "interpretation",
            KnowledgeEvidenceLink.fragment_ref == "summary",
        )
    )
    if evidence_link is not None:
        return

    session.add(
        KnowledgeEvidenceLink(
            claim_id=claim_id,
            source_item_id=source_item_id,
            fragment_type="interpretation",
            fragment_ref="summary",
            interpretation_ref="summary",
            support_role="primary",
        )
    )


def _infer_task_status(semantic_summary: str) -> str:
    normalized_summary = _normalize_summary_for_task_status(semantic_summary)
    if any(pattern.search(normalized_summary) for pattern in _OPEN_TASK_STATUS_PATTERNS):
        return "open"
    if any(pattern.search(normalized_summary) for pattern in _DONE_TASK_STATUS_PATTERNS):
        return "done"
    return "open"


def _normalize_summary_for_task_status(semantic_summary: str) -> str:
    normalized_summary = semantic_summary.lower()
    normalized_summary = normalized_summary.replace("isn't", "is not")
    normalized_summary = normalized_summary.replace("isnt", "is not")
    normalized_summary = normalized_summary.replace("wasn't", "was not")
    normalized_summary = normalized_summary.replace("wasnt", "was not")
    normalized_summary = normalized_summary.replace("aren't", "are not")
    normalized_summary = normalized_summary.replace("arent", "are not")
    return normalized_summary


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
