from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import Projection

_VISIBLE_CLAIM_STATUSES = ("active", "uncertain")


def refresh_assistant_context_projection(session: Session, *, object_ref: str) -> None:
    claims = _collect_relevant_claims(session, object_ref=object_ref)
    related_objects = _load_related_objects(session, claims=claims, object_ref=object_ref)

    assistant_context = {
        "object_ref": object_ref,
        "topic": _serialize_object(related_objects.get(object_ref)),
        "threads": [
            _serialize_object(related_objects.get(thread_ref))
            for thread_ref in sorted(
                claim.subject_ref for claim in claims if claim.claim_type == "membership"
            )
        ],
        "tasks": [
            {
                "task": _serialize_object(related_objects.get(claim.subject_ref)),
                "status_claim": _serialize_claim(claim),
            }
            for claim in claims
            if claim.claim_type == "task_status"
        ],
        "people": [
            {
                "person": _serialize_object(related_objects.get(claim.object_ref_or_value)),
                "claim": _serialize_claim(claim),
            }
            for claim in claims
            if claim.claim_type == "person_hint"
        ],
        "claims": [_serialize_claim(claim) for claim in claims],
    }
    _upsert_projection(
        session,
        object_ref=object_ref,
        projection_type="assistant_context_projection",
        content=assistant_context,
    )


def refresh_topic_status_projection(session: Session, *, object_ref: str) -> None:
    claims = _collect_relevant_claims(session, object_ref=object_ref)
    related_objects = _load_related_objects(session, claims=claims, object_ref=object_ref)

    topic_status = {
        "object_ref": object_ref,
        "topic": _serialize_object(related_objects.get(object_ref)),
        "thread_refs": sorted(
            claim.subject_ref for claim in claims if claim.claim_type == "membership"
        ),
        "task_statuses": [
            {
                "task_ref": claim.subject_ref,
                "task_title": _object_title(related_objects.get(claim.subject_ref)),
                "status_value": claim.object_ref_or_value,
                "claim_status": claim.status,
            }
            for claim in claims
            if claim.claim_type == "task_status"
        ],
        "people": [
            {
                "person_ref": claim.object_ref_or_value,
                "person_title": _object_title(related_objects.get(claim.object_ref_or_value)),
            }
            for claim in claims
            if claim.claim_type == "person_hint"
        ],
        "claim_count": len(claims),
    }
    _upsert_projection(
        session,
        object_ref=object_ref,
        projection_type="topic_status_projection",
        content=topic_status,
    )


def _upsert_projection(
    session: Session,
    *,
    object_ref: str,
    projection_type: str,
    content: dict[str, object],
) -> None:
    projection = session.scalar(
        select(Projection).where(
            Projection.object_ref == object_ref,
            Projection.projection_type == projection_type,
        )
    )
    if projection is None:
        projection = Projection(
            object_ref=object_ref,
            projection_type=projection_type,
            content_json=json.dumps(content, sort_keys=True),
            updated_at=_utc_now(),
        )
        session.add(projection)
        return

    projection.content_json = json.dumps(content, sort_keys=True)
    projection.updated_at = _utc_now()
    session.add(projection)


def _collect_relevant_claims(session: Session, *, object_ref: str) -> list[KnowledgeClaim]:
    membership_claims = session.scalars(
        select(KnowledgeClaim)
        .where(
            KnowledgeClaim.claim_type == "membership",
            KnowledgeClaim.predicate == "belongs_to_topic",
            KnowledgeClaim.object_ref_or_value == object_ref,
            KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES),
        )
        .order_by(KnowledgeClaim.id.asc())
    ).all()
    if not membership_claims:
        return []

    thread_refs = sorted({claim.subject_ref for claim in membership_claims})
    membership_claim_ids = [claim.id for claim in membership_claims]
    source_item_ids = []
    if membership_claim_ids:
        source_item_ids = session.scalars(
            select(KnowledgeEvidenceLink.source_item_id)
            .where(KnowledgeEvidenceLink.claim_id.in_(membership_claim_ids))
            .distinct()
        ).all()

    person_claims = []
    if thread_refs:
        person_claims = session.scalars(
            select(KnowledgeClaim)
            .where(
                KnowledgeClaim.claim_type == "person_hint",
                KnowledgeClaim.subject_ref.in_(thread_refs),
                KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES),
            )
            .order_by(KnowledgeClaim.id.asc())
        ).all()

    task_claims = []
    if source_item_ids:
        task_claims = session.scalars(
            select(KnowledgeClaim)
            .join(KnowledgeEvidenceLink, KnowledgeEvidenceLink.claim_id == KnowledgeClaim.id)
            .where(
                KnowledgeClaim.claim_type == "task_status",
                KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES),
                KnowledgeEvidenceLink.source_item_id.in_(source_item_ids),
            )
            .order_by(KnowledgeClaim.id.asc())
        ).all()

    claims_by_identity: dict[tuple[str, str, str, str], KnowledgeClaim] = {}
    for claim in [*membership_claims, *person_claims, *task_claims]:
        identity = (
            claim.claim_type,
            claim.subject_ref,
            claim.predicate,
            claim.object_ref_or_value,
        )
        claims_by_identity[identity] = claim

    return sorted(
        claims_by_identity.values(),
        key=lambda claim: (
            claim.claim_type,
            claim.subject_ref,
            claim.predicate,
            claim.object_ref_or_value,
            claim.id,
        ),
    )


def _load_related_objects(
    session: Session,
    *,
    claims: list[KnowledgeClaim],
    object_ref: str,
) -> dict[str, KnowledgeObject]:
    related_refs = {object_ref}
    for claim in claims:
        related_refs.add(claim.subject_ref)
        if ":" in claim.object_ref_or_value:
            related_refs.add(claim.object_ref_or_value)

    objects = session.scalars(
        select(KnowledgeObject).where(KnowledgeObject.slug.in_(sorted(related_refs)))
    ).all()
    return {knowledge_object.slug: knowledge_object for knowledge_object in objects}


def _serialize_claim(claim: KnowledgeClaim) -> dict[str, object]:
    return {
        "claim_type": claim.claim_type,
        "subject_ref": claim.subject_ref,
        "predicate": claim.predicate,
        "object_ref_or_value": claim.object_ref_or_value,
        "status": claim.status,
        "confidence_score": claim.confidence_score,
        "observed_at": claim.observed_at.isoformat(),
    }


def _serialize_object(knowledge_object: KnowledgeObject | None) -> dict[str, object] | None:
    if knowledge_object is None:
        return None
    return {
        "object_ref": knowledge_object.slug,
        "object_type": knowledge_object.object_type,
        "title": knowledge_object.title,
        "status": knowledge_object.status,
        "confidence_score": knowledge_object.confidence_score,
    }


def _object_title(knowledge_object: KnowledgeObject | None) -> str | None:
    if knowledge_object is None:
        return None
    return knowledge_object.title


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
