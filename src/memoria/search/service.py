from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import ContentFragment
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import Projection
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourcePayloadScreenshot
from memoria.domain.models import SourceItem
from memoria.screenshots.read.filters import ScreenshotReadFilters
from memoria.screenshots.read.filters import build_screenshot_filter_clauses
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
    filters: ScreenshotReadFilters | None = None,
) -> HybridSearchResult:
    normalized_limit = max(limit, 0)
    normalized_offset = max(offset, 0)
    if not _TOKEN_RE.findall(query.lower()):
        return HybridSearchResult(query=query, items=[], limit=normalized_limit, offset=normalized_offset)

    allowed_source_ids = _resolve_allowed_source_ids(session, filters=filters)
    if allowed_source_ids is not None and not allowed_source_ids:
        return HybridSearchResult(query=query, items=[], limit=normalized_limit, offset=normalized_offset)

    fetch_limit = max(normalized_limit * 5, 20)
    if allowed_source_ids is not None:
        fetch_limit = max(fetch_limit, _count_screenshot_sources(session))

    lexical_source_ids = _lexical_source_matches(
        session,
        query=query,
        limit=fetch_limit,
        allowed_source_ids=allowed_source_ids,
    )

    semantic = search_embedding_matches(
        session,
        embedding_type="screenshot_semantic_text",
        query_text=query,
        limit=fetch_limit,
    )
    semantic_matches = [item for item in semantic if item.distance <= 1.25]
    if allowed_source_ids is not None:
        semantic_matches = [item for item in semantic_matches if item.source_item_id in allowed_source_ids]

    knowledge_ids = _knowledge_source_matches(
        session,
        query=query,
        limit=fetch_limit,
        allowed_source_ids=allowed_source_ids,
    )

    score_by_source: dict[int, float] = {}
    match_sources_by_source: dict[int, set[str]] = {}

    for rank, source_item_id in enumerate(lexical_source_ids):
        _add_match(
            score_by_source,
            match_sources_by_source,
            source_item_id=source_item_id,
            source="lexical",
            rank=rank,
        )

    for rank, item in enumerate(semantic_matches):
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


def _knowledge_source_matches(
    session: Session,
    *,
    query: str,
    limit: int,
    allowed_source_ids: set[int] | None = None,
) -> list[int]:
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

    query_stmt = (
        select(KnowledgeEvidenceLink.source_item_id)
        .distinct()
        .join(KnowledgeClaim, KnowledgeClaim.id == KnowledgeEvidenceLink.claim_id)
        .where(
            or_(
                KnowledgeClaim.subject_ref.in_(sorted(object_refs)),
                KnowledgeClaim.object_ref_or_value.in_(sorted(object_refs)),
            )
        )
    )
    if allowed_source_ids is not None:
        query_stmt = query_stmt.where(KnowledgeEvidenceLink.source_item_id.in_(sorted(allowed_source_ids)))

    source_item_ids = session.scalars(query_stmt.limit(limit)).all()
    return [int(source_item_id) for source_item_id in source_item_ids]


def _lexical_source_matches(
    session: Session,
    *,
    query: str,
    limit: int,
    allowed_source_ids: set[int] | None,
) -> list[int]:
    if allowed_source_ids is None:
        lexical = search_screenshots(
            session,
            query=query,
            limit=limit,
            offset=0,
        )
        return [item.source_item_id for item in lexical.items]
    if not allowed_source_ids:
        return []

    source_item_ids = _filtered_lexical_source_ids_via_fts(
        session,
        query=query,
        limit=limit,
        allowed_source_ids=allowed_source_ids,
    )
    if source_item_ids:
        return source_item_ids

    return _filtered_lexical_source_ids_via_like(
        session,
        query=query,
        limit=limit,
        allowed_source_ids=allowed_source_ids,
    )


def _filtered_lexical_source_ids_via_fts(
    session: Session,
    *,
    query: str,
    limit: int,
    allowed_source_ids: set[int],
) -> list[int]:
    match_query = _fts_query(query)
    if not match_query:
        return []

    id_params = {
        f"source_item_id_{index}": source_item_id
        for index, source_item_id in enumerate(sorted(allowed_source_ids))
    }
    id_placeholders = ", ".join(f":{name}" for name in id_params)
    fragment_limit = max(limit, _count_fragments_for_sources(session, allowed_source_ids))
    rows = session.execute(
        text(
            f"""
            SELECT
                cf.source_item_id,
                cf.id AS fragment_id
            FROM content_fragments_fts
            JOIN content_fragments AS cf ON cf.id = content_fragments_fts.rowid
            WHERE content_fragments_fts MATCH :match_query
              AND cf.source_item_id IN ({id_placeholders})
            ORDER BY bm25(content_fragments_fts), cf.id ASC
            LIMIT :fragment_limit
            """
        ),
        {"match_query": match_query, "fragment_limit": fragment_limit, **id_params},
    ).mappings().all()

    ordered_source_ids: list[int] = []
    seen_source_ids: set[int] = set()
    for row in rows:
        source_item_id = int(row["source_item_id"])
        if source_item_id in seen_source_ids:
            continue
        seen_source_ids.add(source_item_id)
        ordered_source_ids.append(source_item_id)
        if len(ordered_source_ids) >= limit:
            break

    return ordered_source_ids


def _filtered_lexical_source_ids_via_like(
    session: Session,
    *,
    query: str,
    limit: int,
    allowed_source_ids: set[int],
) -> list[int]:
    tokens = _tokenize(query)
    if not tokens:
        return []

    clauses = [ContentFragment.fragment_text.ilike(f"%{token}%") for token in tokens]
    source_item_ids = session.scalars(
        select(ContentFragment.source_item_id)
        .where(
            ContentFragment.source_item_id.in_(sorted(allowed_source_ids)),
            or_(*clauses),
        )
        .group_by(ContentFragment.source_item_id)
        .order_by(func.min(ContentFragment.id), ContentFragment.source_item_id.asc())
        .limit(limit)
    ).all()
    return [int(source_item_id) for source_item_id in source_item_ids]


def _resolve_allowed_source_ids(
    session: Session,
    *,
    filters: ScreenshotReadFilters | None,
) -> set[int] | None:
    if filters is None or not filters.has_any():
        return None

    allowed_source_ids = session.scalars(
        select(SourceItem.id)
        .where(SourceItem.source_type == "screenshot", *build_screenshot_filter_clauses(filters))
    ).all()
    return {int(source_item_id) for source_item_id in allowed_source_ids}


def _count_screenshot_sources(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(SourceItem).where(SourceItem.source_type == "screenshot")
        )
        or 0
    )


def _count_fragments_for_sources(session: Session, source_item_ids: set[int]) -> int:
    if not source_item_ids:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(ContentFragment)
            .where(ContentFragment.source_item_id.in_(sorted(source_item_ids)))
        )
        or 0
    )


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.lower())


def _fts_query(value: str) -> str:
    tokens = _tokenize(value)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


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
