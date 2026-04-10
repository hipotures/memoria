from __future__ import annotations

import json
import re

from sqlalchemy import exists
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import AssetOcrText
from memoria.domain.models import Blob
from memoria.domain.models import ContentFragment
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import PipelineRun
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.domain.models import StageResult
from memoria.screenshots.read.contracts import ScreenshotBlobMetadata
from memoria.screenshots.read.contracts import ScreenshotBlobResult
from memoria.screenshots.read.contracts import ScreenshotContentFragment
from memoria.screenshots.read.contracts import ScreenshotDetail
from memoria.screenshots.read.contracts import ScreenshotInterpretationPayload
from memoria.screenshots.read.contracts import ScreenshotKnowledgeClaim
from memoria.screenshots.read.contracts import ScreenshotKnowledgeSummary
from memoria.screenshots.read.contracts import ScreenshotListItem
from memoria.screenshots.read.contracts import ScreenshotListResult
from memoria.screenshots.read.contracts import ScreenshotOcrPayload
from memoria.screenshots.read.contracts import ScreenshotPipelineRun
from memoria.screenshots.read.contracts import ScreenshotSearchHit
from memoria.screenshots.read.contracts import ScreenshotSearchResult
from memoria.screenshots.read.contracts import ScreenshotStageResult
from memoria.storage.blob_store import load_blob_bytes_for_source_item

_VISIBLE_CLAIM_STATUSES = ("active", "uncertain")
_SEARCH_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FRAGMENT_TYPE_PRIORITY = {
    "ocr_text": 0,
    "scene_description": 1,
}


def list_screenshots(
    session: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    connector_instance_id: str | None = None,
    has_knowledge: bool | None = None,
    q: str | None = None,
) -> ScreenshotListResult:
    normalized_limit = max(limit, 0)
    normalized_offset = max(offset, 0)

    query = (
        select(SourceItem.id)
        .join(SourcePayloadScreenshot, SourcePayloadScreenshot.source_item_id == SourceItem.id)
        .outerjoin(AssetOcrText, AssetOcrText.source_item_id == SourceItem.id)
        .outerjoin(AssetInterpretation, AssetInterpretation.source_item_id == SourceItem.id)
        .where(SourceItem.source_type == "screenshot")
    )

    if connector_instance_id is not None:
        query = query.where(SourceItem.connector_instance_id == connector_instance_id)

    evidence_exists = exists(
        select(KnowledgeEvidenceLink.id).where(KnowledgeEvidenceLink.source_item_id == SourceItem.id)
    )
    if has_knowledge is True:
        query = query.where(evidence_exists)
    elif has_knowledge is False:
        query = query.where(~evidence_exists)

    if q:
        like_term = f"%{q}%"
        query = query.where(
            or_(
                SourcePayloadScreenshot.original_filename.ilike(like_term),
                AssetOcrText.text_content.ilike(like_term),
                AssetInterpretation.semantic_summary.ilike(like_term),
            )
        )

    source_item_ids = session.scalars(
        query.order_by(
            func.coalesce(
                SourceItem.source_observed_at,
                SourceItem.source_created_at,
                SourceItem.ingested_at,
            ).desc(),
            SourceItem.id.desc(),
        )
        .offset(normalized_offset)
        .limit(normalized_limit)
    ).all()

    return ScreenshotListResult(
        items=[_build_list_item(session, source_item_id=source_item_id) for source_item_id in source_item_ids],
        limit=normalized_limit,
        offset=normalized_offset,
    )


def get_screenshot_detail(
    session: Session,
    *,
    source_item_id: int,
) -> ScreenshotDetail | None:
    source_item = session.get(SourceItem, source_item_id)
    if source_item is None or source_item.source_type != "screenshot":
        return None

    payload = session.get(SourcePayloadScreenshot, source_item_id)
    blob = session.get(Blob, source_item.blob_id)
    if payload is None or blob is None:
        return None

    ocr_row = session.get(AssetOcrText, source_item_id)
    interpretation_row = session.get(AssetInterpretation, source_item_id)
    content_fragments = session.scalars(
        select(ContentFragment)
        .where(ContentFragment.source_item_id == source_item_id)
        .order_by(ContentFragment.id.asc())
    ).all()
    pipeline = _load_pipeline_run(session, source_item_id=source_item_id)
    claims = _load_visible_claims(session, source_item_id=source_item_id)

    return ScreenshotDetail(
        source_item_id=source_item.id,
        filename=payload.original_filename,
        media_type=payload.media_type,
        connector_instance_id=source_item.connector_instance_id,
        external_id=source_item.external_id,
        created_at=source_item.source_created_at,
        observed_at=source_item.source_observed_at,
        ingested_at=source_item.ingested_at,
        blob=ScreenshotBlobMetadata(
            media_type=blob.media_type,
            byte_size=blob.byte_size,
            download_url=f"/screenshots/{source_item_id}/blob",
        ),
        ocr=_serialize_ocr_payload(ocr_row),
        interpretation=_serialize_interpretation_payload(interpretation_row),
        content_fragments=[
            ScreenshotContentFragment(
                fragment_type=fragment.fragment_type,
                fragment_ref=fragment.fragment_ref,
                fragment_text=fragment.fragment_text,
                created_at=fragment.created_at,
            )
            for fragment in content_fragments
        ],
        knowledge=ScreenshotKnowledgeSummary(
            object_refs=_load_object_refs(session, claims=claims),
            claims=[
                ScreenshotKnowledgeClaim(
                    claim_id=claim.id,
                    claim_type=claim.claim_type,
                    subject_ref=claim.subject_ref,
                    predicate=claim.predicate,
                    object_ref_or_value=claim.object_ref_or_value,
                    status=claim.status,
                    confidence_score=claim.confidence_score,
                    observed_at=claim.observed_at,
                )
                for claim in claims
            ],
        ),
        pipeline=pipeline,
    )


def search_screenshots(
    session: Session,
    *,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> ScreenshotSearchResult:
    normalized_limit = max(limit, 0)
    normalized_offset = max(offset, 0)
    if not query.strip():
        return ScreenshotSearchResult(query=query, items=[], limit=normalized_limit, offset=normalized_offset)

    try:
        candidates = _search_screenshot_candidates_via_fts(
            session,
            query=query,
            limit=max(normalized_limit * 10, 20),
            offset=0,
        )
    except OperationalError:
        candidates = []
    if not candidates:
        candidates = _search_screenshot_candidates_via_like(
            session,
            query=query,
            limit=max(normalized_limit * 10, 20),
            offset=0,
        )

    winning_candidates = _collapse_candidates(candidates)
    sliced_candidates = winning_candidates[normalized_offset : normalized_offset + normalized_limit]

    items: list[ScreenshotSearchHit] = []
    for candidate in sliced_candidates:
        payload = session.get(SourcePayloadScreenshot, candidate["source_item_id"])
        interpretation_row = session.get(AssetInterpretation, candidate["source_item_id"])
        if payload is None:
            continue
        claims = _load_visible_claims(session, source_item_id=int(candidate["source_item_id"]))
        items.append(
            ScreenshotSearchHit(
                source_item_id=int(candidate["source_item_id"]),
                filename=payload.original_filename,
                match_source=str(candidate["fragment_type"]),
                match_fragment_ref=str(candidate["fragment_ref"]),
                match_text=str(candidate["fragment_text"]),
                semantic_summary=None if interpretation_row is None else interpretation_row.semantic_summary,
                app_hint=None if interpretation_row is None else interpretation_row.app_hint,
                object_refs=_load_object_refs(session, claims=claims),
            )
        )

    return ScreenshotSearchResult(
        query=query,
        items=items,
        limit=normalized_limit,
        offset=normalized_offset,
    )


def open_screenshot_blob(
    session: Session,
    *,
    source_item_id: int,
) -> ScreenshotBlobResult | None:
    try:
        content, media_type = load_blob_bytes_for_source_item(
            session,
            source_item_id=source_item_id,
        )
    except (FileNotFoundError, ValueError):
        return None

    return ScreenshotBlobResult(content=content, media_type=media_type)


def _build_list_item(session: Session, *, source_item_id: int) -> ScreenshotListItem:
    source_item = session.get(SourceItem, source_item_id)
    payload = session.get(SourcePayloadScreenshot, source_item_id)
    assert source_item is not None
    assert payload is not None

    blob = session.get(Blob, source_item.blob_id)
    ocr_row = session.get(AssetOcrText, source_item_id)
    interpretation_row = session.get(AssetInterpretation, source_item_id)
    pipeline = _load_pipeline_run(session, source_item_id=source_item_id)
    claims = _load_visible_claims(session, source_item_id=source_item_id)

    excerpt_source = None
    if ocr_row is not None:
        excerpt_source = ocr_row.text_content
    elif interpretation_row is not None:
        excerpt_source = interpretation_row.semantic_summary

    return ScreenshotListItem(
        source_item_id=source_item.id,
        filename=payload.original_filename,
        media_type=payload.media_type,
        created_at=source_item.source_created_at,
        observed_at=source_item.source_observed_at,
        ingested_at=source_item.ingested_at,
        connector_instance_id=source_item.connector_instance_id,
        pipeline_status=None if pipeline is None else pipeline.status,
        blob_available=bool(
            blob is not None
            and blob.storage_kind == "local"
            and blob.storage_uri
        ),
        ocr_excerpt=_truncate_excerpt(excerpt_source),
        semantic_summary=None if interpretation_row is None else interpretation_row.semantic_summary,
        screen_category=None if interpretation_row is None else interpretation_row.screen_category,
        app_hint=None if interpretation_row is None else interpretation_row.app_hint,
        object_refs=_load_object_refs(session, claims=claims),
    )


def _serialize_ocr_payload(ocr_row: AssetOcrText | None) -> ScreenshotOcrPayload | None:
    if ocr_row is None:
        return None
    return ScreenshotOcrPayload(
        engine_name=ocr_row.engine_name,
        text_content=ocr_row.text_content,
        language_hint=ocr_row.language_hint,
        block_map=_json_loads_or_default(ocr_row.block_map_json, default=[]),
        created_at=ocr_row.created_at,
        updated_at=ocr_row.updated_at,
    )


def _serialize_interpretation_payload(
    interpretation_row: AssetInterpretation | None,
) -> ScreenshotInterpretationPayload | None:
    if interpretation_row is None:
        return None
    return ScreenshotInterpretationPayload(
        screen_category=interpretation_row.screen_category,
        semantic_summary=interpretation_row.semantic_summary,
        app_hint=interpretation_row.app_hint,
        topic_candidates=_json_loads_or_default(interpretation_row.topic_candidates_json, default=[]),
        task_candidates=_json_loads_or_default(interpretation_row.task_candidates_json, default=[]),
        person_candidates=_json_loads_or_default(interpretation_row.person_candidates_json, default=[]),
        confidence=_json_loads_or_default(interpretation_row.confidence_json, default={}),
        created_at=interpretation_row.created_at,
        updated_at=interpretation_row.updated_at,
    )


def _load_pipeline_run(session: Session, *, source_item_id: int) -> ScreenshotPipelineRun | None:
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.source_item_id == source_item_id)
        .order_by(PipelineRun.id.desc())
    )
    if pipeline_run is None:
        return None

    stage_results = session.scalars(
        select(StageResult)
        .where(StageResult.pipeline_run_id == pipeline_run.id)
        .order_by(StageResult.started_at.asc(), StageResult.id.asc())
    ).all()

    return ScreenshotPipelineRun(
        pipeline_run_id=pipeline_run.id,
        pipeline_name=pipeline_run.pipeline_name,
        status=pipeline_run.status,
        run_reason=pipeline_run.run_reason,
        started_at=pipeline_run.started_at,
        finished_at=pipeline_run.finished_at,
        stage_results=[
            ScreenshotStageResult(
                stage_name=stage.stage_name,
                status=stage.status,
                attempt=stage.attempt,
                output_payload=_json_loads_or_default(stage.output_json, default=None),
                error_text=stage.error_text,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
            )
            for stage in stage_results
        ],
    )


def _load_visible_claims(session: Session, *, source_item_id: int) -> list[KnowledgeClaim]:
    return session.scalars(
        select(KnowledgeClaim)
        .distinct()
        .join(KnowledgeEvidenceLink, KnowledgeEvidenceLink.claim_id == KnowledgeClaim.id)
        .where(
            KnowledgeEvidenceLink.source_item_id == source_item_id,
            KnowledgeClaim.status.in_(_VISIBLE_CLAIM_STATUSES),
        )
        .order_by(
            KnowledgeClaim.claim_type.asc(),
            KnowledgeClaim.subject_ref.asc(),
            KnowledgeClaim.predicate.asc(),
            KnowledgeClaim.object_ref_or_value.asc(),
            KnowledgeClaim.id.asc(),
        )
    ).all()


def _load_object_refs(session: Session, *, claims: list[KnowledgeClaim]) -> list[str]:
    object_like_refs = sorted(
        {
            claim.object_ref_or_value
            for claim in claims
            if ":" in claim.object_ref_or_value
        }
    )
    existing_object_refs = set(
        session.scalars(
            select(KnowledgeObject.slug).where(KnowledgeObject.slug.in_(object_like_refs))
        ).all()
    )

    refs = {claim.subject_ref for claim in claims}
    refs.update(ref for ref in object_like_refs if ref in existing_object_refs)
    return sorted(refs)


def _truncate_excerpt(value: str | None, *, limit: int = 200) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) <= limit:
        return trimmed
    return f"{trimmed[: limit - 1].rstrip()}…"


def _search_screenshot_candidates_via_fts(
    session: Session,
    *,
    query: str,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    match_query = _fts_query(query)
    if not match_query:
        return []

    rows = session.execute(
        text(
            """
            SELECT
                cf.id AS fragment_id,
                cf.source_item_id,
                cf.fragment_type,
                cf.fragment_ref,
                cf.fragment_text,
                bm25(content_fragments_fts) AS rank
            FROM content_fragments_fts
            JOIN content_fragments AS cf ON cf.id = content_fragments_fts.rowid
            WHERE content_fragments_fts MATCH :match_query
            ORDER BY bm25(content_fragments_fts), cf.id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"match_query": match_query, "limit": limit, "offset": offset},
    ).mappings().all()

    return [
        {
            "source_item_id": int(row["source_item_id"]),
            "fragment_id": int(row["fragment_id"]),
            "fragment_type": str(row["fragment_type"]),
            "fragment_ref": str(row["fragment_ref"]),
            "fragment_text": str(row["fragment_text"]),
            "rank": float(row["rank"]),
        }
        for row in rows
    ]


def _search_screenshot_candidates_via_like(
    session: Session,
    *,
    query: str,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    tokens = _tokenize(query)
    if not tokens:
        return []

    clauses = [ContentFragment.fragment_text.ilike(f"%{token}%") for token in tokens]
    fragments = session.scalars(
        select(ContentFragment)
        .where(or_(*clauses))
        .order_by(ContentFragment.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        {
            "source_item_id": fragment.source_item_id,
            "fragment_id": fragment.id,
            "fragment_type": fragment.fragment_type,
            "fragment_ref": fragment.fragment_ref,
            "fragment_text": fragment.fragment_text,
            "rank": float(fragment.id),
        }
        for fragment in fragments
    ]


def _collapse_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    winners_by_source_item_id: dict[int, dict[str, object]] = {}
    for candidate in candidates:
        source_item_id = int(candidate["source_item_id"])
        incumbent = winners_by_source_item_id.get(source_item_id)
        if incumbent is None or _candidate_sort_key(candidate) < _candidate_sort_key(incumbent):
            winners_by_source_item_id[source_item_id] = candidate

    return sorted(winners_by_source_item_id.values(), key=_candidate_sort_key)


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[float, int, int]:
    return (
        float(candidate["rank"]),
        _fragment_priority(str(candidate["fragment_type"])),
        int(candidate["fragment_id"]),
    )


def _fragment_priority(fragment_type: str) -> int:
    return _FRAGMENT_TYPE_PRIORITY.get(fragment_type, 10)


def _fts_query(value: str) -> str:
    tokens = _tokenize(value)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def _tokenize(value: str) -> list[str]:
    return _SEARCH_TOKEN_RE.findall(value.lower())


def _json_loads_or_default(payload: str | None, *, default):
    if payload is None:
        return default
    return json.loads(payload)
