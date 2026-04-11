from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import Projection
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourcePayloadScreenshot
from memoria.screenshots.read.service import search_screenshots
from memoria.search.embeddings import search_embedding_matches

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class HybridSearchHit:
    source_item_id: int
    filename: str
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]
    match_sources: list[str]
    score: float
    cluster_key: str | None


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    query: str
    items: list[HybridSearchHit]
    limit: int
    offset: int


def hybrid_search_screenshots(
    session: Session,
    *,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> HybridSearchResult:
    normalized_limit = max(limit, 0)
    normalized_offset = max(offset, 0)
    if not _TOKEN_RE.findall(query.lower()):
        return HybridSearchResult(query=query, items=[], limit=normalized_limit, offset=normalized_offset)

    lexical = search_screenshots(
        session,
        query=query,
        limit=max(normalized_limit * 5, 20),
        offset=0,
    )
    semantic = search_embedding_matches(
        session,
        embedding_type="screenshot_semantic_text",
        query_text=query,
        limit=max(normalized_limit * 5, 20),
    )
    knowledge_ids = _knowledge_source_matches(
        session,
        query=query,
        limit=max(normalized_limit * 5, 20),
    )

    score_by_source: dict[int, float] = {}
    match_sources_by_source: dict[int, set[str]] = {}

    for rank, item in enumerate(lexical.items):
        _add_match(
            score_by_source,
            match_sources_by_source,
            source_item_id=item.source_item_id,
            source="lexical",
            rank=rank,
        )

    for rank, item in enumerate(semantic):
        if item.distance > 1.25:
            continue
        _add_match(
            score_by_source,
            match_sources_by_source,
            source_item_id=item.source_item_id,
            source="semantic",
            rank=rank,
        )

    for rank, source_item_id in enumerate(knowledge_ids):
        _add_match(
            score_by_source,
            match_sources_by_source,
            source_item_id=source_item_id,
            source="knowledge",
            rank=rank,
        )

    ordered_source_ids = sorted(
        score_by_source,
        key=lambda source_item_id: (-score_by_source[source_item_id], source_item_id),
    )
    sliced_source_ids = ordered_source_ids[normalized_offset : normalized_offset + normalized_limit]

    return HybridSearchResult(
        query=query,
        items=[
            _build_hybrid_search_hit(
                session,
                source_item_id=source_item_id,
                score=score_by_source[source_item_id],
                match_sources=sorted(match_sources_by_source[source_item_id]),
            )
            for source_item_id in sliced_source_ids
        ],
        limit=normalized_limit,
        offset=normalized_offset,
    )


def _build_hybrid_search_hit(
    session: Session,
    *,
    source_item_id: int,
    score: float,
    match_sources: list[str],
) -> HybridSearchHit:
    payload = session.get(SourcePayloadScreenshot, source_item_id)
    interpretation = session.get(AssetInterpretation, source_item_id)
    latest_map_run_id = session.scalar(
        select(SemanticMapRun.id)
        .where(SemanticMapRun.map_key == "screenshots_semantic_v1")
        .order_by(SemanticMapRun.id.desc())
    )
    cluster_key = None
    if latest_map_run_id is not None:
        cluster_key = session.scalar(
            select(SemanticMapPoint.cluster_key).where(
                SemanticMapPoint.map_run_id == latest_map_run_id,
                SemanticMapPoint.source_item_id == source_item_id,
            )
        )

    return HybridSearchHit(
        source_item_id=source_item_id,
        filename="" if payload is None else payload.original_filename,
        semantic_summary=None if interpretation is None else interpretation.semantic_summary,
        app_hint=None if interpretation is None else interpretation.app_hint,
        object_refs=_load_object_refs(session, source_item_id=source_item_id),
        match_sources=match_sources,
        score=score,
        cluster_key=cluster_key,
    )


def _knowledge_source_matches(session: Session, *, query: str, limit: int) -> list[int]:
    like_term = f"%{query}%"
    object_refs = set(
        session.scalars(
            select(KnowledgeObject.slug).where(
                or_(
                    KnowledgeObject.slug.ilike(like_term),
                    KnowledgeObject.title.ilike(like_term),
                )
            )
        ).all()
    )
    object_refs.update(
        session.scalars(
            select(Projection.object_ref).where(Projection.content_json.ilike(like_term))
        ).all()
    )
    if not object_refs:
        return []

    source_item_ids = session.scalars(
        select(KnowledgeEvidenceLink.source_item_id)
        .distinct()
        .join(KnowledgeClaim, KnowledgeClaim.id == KnowledgeEvidenceLink.claim_id)
        .where(
            or_(
                KnowledgeClaim.subject_ref.in_(sorted(object_refs)),
                KnowledgeClaim.object_ref_or_value.in_(sorted(object_refs)),
            )
        )
        .limit(limit)
    ).all()
    return [int(source_item_id) for source_item_id in source_item_ids]


def _load_object_refs(session: Session, *, source_item_id: int) -> list[str]:
    claims = session.scalars(
        select(KnowledgeClaim)
        .distinct()
        .join(KnowledgeEvidenceLink, KnowledgeEvidenceLink.claim_id == KnowledgeClaim.id)
        .where(KnowledgeEvidenceLink.source_item_id == source_item_id)
    ).all()
    refs = {claim.subject_ref for claim in claims}
    refs.update(claim.object_ref_or_value for claim in claims if ":" in claim.object_ref_or_value)
    existing_refs = set(
        session.scalars(select(KnowledgeObject.slug).where(KnowledgeObject.slug.in_(sorted(refs)))).all()
    )
    return sorted(ref for ref in refs if ref in existing_refs or ref.startswith("thread:"))


def _add_match(
    score_by_source: dict[int, float],
    match_sources_by_source: dict[int, set[str]],
    *,
    source_item_id: int,
    source: str,
    rank: int,
) -> None:
    score_by_source[source_item_id] = score_by_source.get(source_item_id, 0.0) + _rrf(rank)
    match_sources_by_source.setdefault(source_item_id, set()).add(source)


def _rrf(rank: int, *, k: int = 60) -> float:
    return 1.0 / float(k + rank + 1)
