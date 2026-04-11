from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.knowledge.read.contracts import KnowledgeClaimSummary
from memoria.knowledge.read.contracts import KnowledgeEvidenceSummary
from memoria.knowledge.read.contracts import KnowledgeObjectSummary
from memoria.knowledge.read.contracts import KnowledgeScreenshotSummary
from memoria.knowledge.read.contracts import KnowledgeTaskStatusSummary
from memoria.knowledge.read.contracts import ThreadReadModel
from memoria.knowledge.read.contracts import TopicReadModel

_VISIBLE_CLAIM_STATUSES = ("active", "uncertain")


def get_topic_view(session: Session, *, slug: str) -> TopicReadModel | None:
    topic_ref = _normalize_object_ref("topic", slug)
    topic = _load_object(session, topic_ref=topic_ref)
    if topic is None:
        return None

    membership_claims = _load_claims(
        session,
        claim_type="membership",
        predicate="belongs_to_topic",
        object_ref_or_values=[topic_ref],
    )
    thread_refs = sorted({claim.subject_ref for claim in membership_claims})
    person_claims = _load_claims(
        session,
        claim_type="person_hint",
        subject_refs=thread_refs,
    )
    task_source_item_ids = _source_item_ids_for_claims(session, [*membership_claims, *person_claims])
    task_claims = _load_claims(
        session,
        claim_type="task_status",
        source_item_ids=task_source_item_ids,
    )
    claims = _dedupe_claims([*membership_claims, *person_claims, *task_claims])

    return TopicReadModel(
        topic=_serialize_object(topic),
        thread_refs=thread_refs,
        task_statuses=_serialize_task_statuses(session, task_claims),
        people=_serialize_people(session, person_claims),
        recent_screenshots=_load_recent_screenshots(session, claims=claims),
        evidence=_load_evidence(session, claims=claims),
    )


def get_thread_view(session: Session, *, slug: str) -> ThreadReadModel | None:
    thread_ref = _normalize_object_ref("thread", slug)
    thread = _load_object(session, topic_ref=thread_ref)
    if thread is None:
        return None

    membership_claims = _load_claims(
        session,
        claim_type="membership",
        predicate="belongs_to_topic",
        subject_refs=[thread_ref],
    )
    topic_ref = membership_claims[0].object_ref_or_value if membership_claims else None
    person_claims = _load_claims(
        session,
        claim_type="person_hint",
        subject_refs=[thread_ref],
    )
    task_source_item_ids = _source_item_ids_for_claims(session, [*membership_claims, *person_claims])
    task_claims = _load_claims(
        session,
        claim_type="task_status",
        source_item_ids=task_source_item_ids,
    )
    claims = _dedupe_claims([*membership_claims, *person_claims, *task_claims])

    return ThreadReadModel(
        thread=_serialize_object(thread),
        topic_ref=topic_ref,
        people=_serialize_people(session, person_claims),
        claims=[_serialize_claim(claim) for claim in claims],
        recent_screenshots=_load_recent_screenshots(session, claims=claims),
        evidence=_load_evidence(session, claims=claims),
    )


def _normalize_object_ref(prefix: str, slug: str) -> str:
    if slug.startswith(f"{prefix}:"):
        return slug
    return f"{prefix}:{slug}"


def _load_object(session: Session, *, topic_ref: str) -> KnowledgeObject | None:
    return session.scalar(select(KnowledgeObject).where(KnowledgeObject.slug == topic_ref))


def _load_claims(
    session: Session,
    *,
    claim_type: str | None = None,
    predicate: str | None = None,
    subject_refs: list[str] | None = None,
    object_ref_or_values: list[str] | None = None,
    source_item_ids: list[int] | None = None,
) -> list[KnowledgeClaim]:
    query = select(KnowledgeClaim).where(KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES))
    if source_item_ids is not None:
        if not source_item_ids:
            return []
        query = query.distinct().join(
            KnowledgeEvidenceLink,
            KnowledgeEvidenceLink.claim_id == KnowledgeClaim.id,
        )
        query = query.where(KnowledgeEvidenceLink.source_item_id.in_(sorted(set(source_item_ids))))
    if claim_type is not None:
        query = query.where(KnowledgeClaim.claim_type == claim_type)
    if predicate is not None:
        query = query.where(KnowledgeClaim.predicate == predicate)
    if subject_refs is not None:
        if not subject_refs:
            return []
        query = query.where(KnowledgeClaim.subject_ref.in_(sorted(set(subject_refs))))
    if object_ref_or_values is not None:
        if not object_ref_or_values:
            return []
        query = query.where(KnowledgeClaim.object_ref_or_value.in_(sorted(set(object_ref_or_values))))
    return session.scalars(query.order_by(KnowledgeClaim.id.asc())).all()


def _source_item_ids_for_claims(session: Session, claims: list[KnowledgeClaim]) -> list[int]:
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return []
    return [
        int(source_item_id)
        for source_item_id in session.scalars(
            select(KnowledgeEvidenceLink.source_item_id)
            .where(KnowledgeEvidenceLink.claim_id.in_(sorted(set(claim_ids))))
            .distinct()
        ).all()
    ]


def _load_recent_screenshots(
    session: Session,
    *,
    claims: list[KnowledgeClaim],
) -> list[KnowledgeScreenshotSummary]:
    source_item_ids = _source_item_ids_for_claims(session, claims)
    if not source_item_ids:
        return []

    object_refs_by_source_item_id = _object_refs_by_source_item_id(session, source_item_ids=source_item_ids)
    source_items = session.scalars(
        select(SourceItem)
        .join(SourcePayloadScreenshot, SourcePayloadScreenshot.source_item_id == SourceItem.id)
        .outerjoin(AssetInterpretation, AssetInterpretation.source_item_id == SourceItem.id)
        .where(SourceItem.id.in_(sorted(set(source_item_ids))))
        .order_by(
            func.coalesce(
                SourceItem.source_observed_at,
                SourceItem.source_created_at,
                SourceItem.ingested_at,
            ).desc(),
            SourceItem.id.desc(),
        )
    ).all()

    summaries: list[KnowledgeScreenshotSummary] = []
    for source_item in source_items:
        payload = session.get(SourcePayloadScreenshot, source_item.id)
        interpretation = session.get(AssetInterpretation, source_item.id)
        if payload is None:
            continue
        summaries.append(
            KnowledgeScreenshotSummary(
                source_item_id=source_item.id,
                filename=payload.original_filename,
                semantic_summary=None if interpretation is None else interpretation.semantic_summary,
                app_hint=None if interpretation is None else interpretation.app_hint,
                observed_at=source_item.source_observed_at,
                object_refs=object_refs_by_source_item_id.get(source_item.id, []),
            )
        )
    return summaries


def _load_evidence(
    session: Session,
    *,
    claims: list[KnowledgeClaim],
) -> list[KnowledgeEvidenceSummary]:
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return []

    rows = session.execute(
        select(
            KnowledgeEvidenceLink.id,
            KnowledgeEvidenceLink.claim_id,
            KnowledgeEvidenceLink.source_item_id,
            KnowledgeEvidenceLink.fragment_type,
            KnowledgeEvidenceLink.fragment_ref,
            KnowledgeEvidenceLink.support_role,
            SourceItem.source_observed_at,
            SourceItem.source_created_at,
            SourceItem.ingested_at,
        )
        .join(SourceItem, SourceItem.id == KnowledgeEvidenceLink.source_item_id)
        .where(KnowledgeEvidenceLink.claim_id.in_(sorted(set(claim_ids))))
        .order_by(
            func.coalesce(
                SourceItem.source_observed_at,
                SourceItem.source_created_at,
                SourceItem.ingested_at,
            ).desc(),
            KnowledgeEvidenceLink.id.asc(),
        )
    ).all()

    seen: set[tuple[int, int, str, str, str]] = set()
    evidence: list[KnowledgeEvidenceSummary] = []
    for row in rows:
        identity = (
            int(row.claim_id),
            int(row.source_item_id),
            str(row.fragment_type),
            str(row.fragment_ref),
            str(row.support_role),
        )
        if identity in seen:
            continue
        seen.add(identity)
        evidence.append(
            KnowledgeEvidenceSummary(
                claim_id=int(row.claim_id),
                source_item_id=int(row.source_item_id),
                fragment_type=str(row.fragment_type),
                fragment_ref=str(row.fragment_ref),
                support_role=str(row.support_role),
            )
        )
    return evidence


def _object_refs_by_source_item_id(
    session: Session,
    *,
    source_item_ids: list[int],
) -> dict[int, list[str]]:
    if not source_item_ids:
        return {}

    rows = session.execute(
        select(
            KnowledgeEvidenceLink.source_item_id,
            KnowledgeClaim.subject_ref,
            KnowledgeClaim.object_ref_or_value,
        )
        .join(KnowledgeClaim, KnowledgeClaim.id == KnowledgeEvidenceLink.claim_id)
        .where(
            KnowledgeEvidenceLink.source_item_id.in_(sorted(set(source_item_ids))),
            KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES),
        )
    ).all()

    refs_by_source_item_id: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        source_item_id = int(row.source_item_id)
        refs_by_source_item_id[source_item_id].add(str(row.subject_ref))
        if ":" in str(row.object_ref_or_value):
            refs_by_source_item_id[source_item_id].add(str(row.object_ref_or_value))

    existing_refs = set(
        session.scalars(
            select(KnowledgeObject.slug).where(KnowledgeObject.slug.in_(sorted({
                ref
                for refs in refs_by_source_item_id.values()
                for ref in refs
            })))
        ).all()
    )
    result: dict[int, list[str]] = {}
    for source_item_id, refs in refs_by_source_item_id.items():
        result[source_item_id] = sorted(
            ref for ref in refs if ref in existing_refs or ref.startswith("thread:")
        )
    return result


def _serialize_object(knowledge_object: KnowledgeObject) -> KnowledgeObjectSummary:
    return KnowledgeObjectSummary(
        object_ref=knowledge_object.slug,
        object_type=knowledge_object.object_type,
        title=knowledge_object.title,
        status=knowledge_object.status,
        confidence_score=knowledge_object.confidence_score,
    )


def _serialize_people(
    session: Session,
    claims: list[KnowledgeClaim],
) -> list[KnowledgeObjectSummary]:
    person_refs = sorted({claim.object_ref_or_value for claim in claims if ":" in claim.object_ref_or_value})
    if not person_refs:
        return []
    objects = session.scalars(
        select(KnowledgeObject)
        .where(KnowledgeObject.slug.in_(person_refs))
        .order_by(KnowledgeObject.title.asc(), KnowledgeObject.slug.asc())
    ).all()
    return [_serialize_object(knowledge_object) for knowledge_object in objects if knowledge_object.object_type == "person"]


def _serialize_task_statuses(
    session: Session,
    claims: list[KnowledgeClaim],
) -> list[KnowledgeTaskStatusSummary]:
    if not claims:
        return []
    task_refs = sorted({claim.subject_ref for claim in claims})
    task_titles = {
        knowledge_object.slug: knowledge_object.title
        for knowledge_object in session.scalars(
            select(KnowledgeObject).where(KnowledgeObject.slug.in_(task_refs))
        ).all()
    }
    return [
        KnowledgeTaskStatusSummary(
            task_ref=claim.subject_ref,
            task_title=task_titles.get(claim.subject_ref),
            status_value=claim.object_ref_or_value,
            claim_status=claim.status,
        )
        for claim in claims
    ]


def _serialize_claim(claim: KnowledgeClaim) -> KnowledgeClaimSummary:
    return KnowledgeClaimSummary(
        claim_id=claim.id,
        claim_type=claim.claim_type,
        subject_ref=claim.subject_ref,
        predicate=claim.predicate,
        object_ref_or_value=claim.object_ref_or_value,
        status=claim.status,
        confidence_score=claim.confidence_score,
        observed_at=claim.observed_at,
    )


def _dedupe_claims(claims: Iterable[KnowledgeClaim]) -> list[KnowledgeClaim]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[KnowledgeClaim] = []
    for claim in claims:
        identity = (
            claim.claim_type,
            claim.subject_ref,
            claim.predicate,
            claim.object_ref_or_value,
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(claim)
    return deduped
