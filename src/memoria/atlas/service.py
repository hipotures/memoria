from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.projection import ATLAS_KEY
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import SourceItem
from memoria.screenshots.read.filters import ScreenshotReadFilters
from memoria.screenshots.read.filters import build_screenshot_filter_clauses

_SECTION_LIMIT = 6
_EMPTY_REGION_SHAPE = {"shape_type": "polygon", "rings": []}


@dataclass(frozen=True, slots=True)
class AtlasOverlay:
    match_count: int = 0


@dataclass(frozen=True, slots=True)
class AtlasRepresentativeRef:
    rank: int
    source_item_id: int


@dataclass(frozen=True, slots=True)
class AtlasBridgeNeighbor:
    edge_type: str
    region_key: str
    weight: float


@dataclass(frozen=True, slots=True)
class AtlasRunView:
    atlas_run_id: int
    atlas_key: str
    status: str
    source_count: int
    source_snapshot_id: str | None
    corpus_hash: str | None
    embedding_type: str
    embedding_model: str
    embedding_version: str
    clustering_method: str
    clustering_params: dict[str, object]
    random_seed: int
    layout_version: str
    generated_at: datetime
    completed_at: datetime | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class AtlasRegionView:
    atlas_run_id: int
    region_key: str
    parent_region_key: str | None
    level: int
    title: str
    x: float
    y: float
    label_x: float
    label_y: float
    region_shape: dict[str, object]
    item_count: int
    top_labels: list[str]
    top_apps: list[str]
    top_people: list[str]
    top_entities: list[str]
    time_start: datetime | None
    time_end: datetime | None
    representatives: list[AtlasRepresentativeRef]
    bridge_neighbors: list[AtlasBridgeNeighbor]
    cohesion_score: float
    overlay: AtlasOverlay = field(default_factory=AtlasOverlay)


@dataclass(frozen=True, slots=True)
class AtlasEdgeView:
    source_region_key: str
    target_region_key: str
    weight: float
    edge_type: str


@dataclass(frozen=True, slots=True)
class AtlasItemView:
    source_item_id: int
    region_key: str
    subregion_key: str | None
    x: float
    y: float
    semantic_summary: str | None
    app_hint: str | None
    observed_at: datetime | None
    object_refs: list[str]
    is_representative: bool
    representative_rank: int | None
    is_bridge: bool
    bridge_type: str | None
    secondary_region_key: str | None
    bridge_score: float
    screenshot_detail_url: str | None


@dataclass(frozen=True, slots=True)
class AtlasItemPage:
    items: list[AtlasItemView]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class AtlasEvidenceSectionTotals:
    representatives: int
    bridges: int
    long_tail: int


@dataclass(frozen=True, slots=True)
class AtlasOverview:
    atlas_run: AtlasRunView | None
    regions: list[AtlasRegionView]
    edges: list[AtlasEdgeView]
    active_filters: ScreenshotReadFilters


@dataclass(frozen=True, slots=True)
class AtlasRegionDetail:
    atlas_run: AtlasRunView
    region: AtlasRegionView
    subregions: list[AtlasRegionView]
    representatives: list[AtlasItemView]
    active_filters: ScreenshotReadFilters


@dataclass(frozen=True, slots=True)
class AtlasEvidenceSlice:
    atlas_run: AtlasRunView
    region_key: str
    subregion_key: str | None
    sort: str
    representatives: list[AtlasItemView]
    bridges: list[AtlasItemView]
    long_tail_page: AtlasItemPage
    section_totals: AtlasEvidenceSectionTotals
    active_filters: ScreenshotReadFilters


def get_atlas_overview(
    session: Session,
    *,
    filters: ScreenshotReadFilters,
) -> AtlasOverview:
    atlas_run = _get_latest_published_run(session)
    if atlas_run is None:
        return AtlasOverview(
            atlas_run=None,
            regions=[],
            edges=[],
            active_filters=filters,
        )

    regions = _load_regions(session, atlas_run_id=atlas_run.id, level=0)
    region_keys = [region.region_key for region in regions]
    overlays = _build_region_overlays(
        session,
        atlas_run_id=atlas_run.id,
        filters=filters,
        group_by="region",
    )
    return AtlasOverview(
        atlas_run=_atlas_run_view(atlas_run),
        regions=_attach_region_overlays(regions, overlays),
        edges=_load_edges(session, atlas_run_id=atlas_run.id, region_keys=region_keys),
        active_filters=filters,
    )


def get_atlas_region_detail(
    session: Session,
    *,
    region_key: str,
    filters: ScreenshotReadFilters,
) -> AtlasRegionDetail | None:
    atlas_run = _get_latest_published_run(session)
    if atlas_run is None:
        return None

    region_row = _load_region_row(session, atlas_run_id=atlas_run.id, region_key=region_key)
    if region_row is None or region_row.level != 0:
        return None

    region_overlay = _build_region_overlays(
        session,
        atlas_run_id=atlas_run.id,
        filters=filters,
        group_by="region",
        region_key=region_key,
    ).get(region_key, AtlasOverlay())
    subregions = _load_regions(
        session,
        atlas_run_id=atlas_run.id,
        parent_region_key=region_key,
    )
    subregion_overlays = _build_region_overlays(
        session,
        atlas_run_id=atlas_run.id,
        filters=filters,
        group_by="subregion",
        region_key=region_key,
    )
    representative_ids = _representative_source_item_ids(region_row)
    return AtlasRegionDetail(
        atlas_run=_atlas_run_view(atlas_run),
        region=_atlas_region_view(region_row, overlay=region_overlay),
        subregions=_attach_region_overlays(subregions, subregion_overlays),
        representatives=_load_items_for_source_item_ids(
            session,
            atlas_run_id=atlas_run.id,
            region_key=region_key,
            subregion_key=None,
            source_item_ids=representative_ids,
            filters=filters,
        ),
        active_filters=filters,
    )


def get_atlas_evidence_slice(
    session: Session,
    *,
    region_key: str,
    subregion_key: str | None,
    sort: str,
    limit: int,
    offset: int,
    filters: ScreenshotReadFilters,
) -> AtlasEvidenceSlice | None:
    atlas_run = _get_latest_published_run(session)
    if atlas_run is None:
        return None

    region_row = _load_region_row(session, atlas_run_id=atlas_run.id, region_key=region_key)
    if region_row is None or region_row.level != 0:
        return None

    projection_row = region_row
    if subregion_key is not None:
        projection_row = _load_region_row(session, atlas_run_id=atlas_run.id, region_key=subregion_key)
        if projection_row is None or projection_row.parent_region_key != region_key:
            return None

    representative_ids = _representative_source_item_ids(projection_row)
    representatives = _load_items_for_source_item_ids(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=subregion_key,
        source_item_ids=representative_ids,
        filters=filters,
        limit=_SECTION_LIMIT,
    )
    representative_source_item_ids = {item.source_item_id for item in representatives}

    bridge_total = _count_items(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        bridge_only=True,
        exclude_source_item_ids=representative_source_item_ids,
    )
    bridges = _load_items(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        bridge_only=True,
        exclude_source_item_ids=representative_source_item_ids,
        limit=_SECTION_LIMIT,
        offset=0,
        sort="bridge_score_desc",
    )
    bridge_source_item_ids = {item.source_item_id for item in bridges}

    long_tail_total = _count_items(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        long_tail_only=True,
        exclude_source_item_ids=representative_source_item_ids | bridge_source_item_ids,
    )
    long_tail_items = _load_items(
        session,
        atlas_run_id=atlas_run.id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        long_tail_only=True,
        exclude_source_item_ids=representative_source_item_ids | bridge_source_item_ids,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return AtlasEvidenceSlice(
        atlas_run=_atlas_run_view(atlas_run),
        region_key=region_key,
        subregion_key=subregion_key,
        sort=sort,
        representatives=representatives,
        bridges=bridges,
        long_tail_page=AtlasItemPage(
            items=long_tail_items,
            limit=limit,
            offset=offset,
            total=long_tail_total,
        ),
        section_totals=AtlasEvidenceSectionTotals(
            representatives=_count_items_for_source_item_ids(
                session,
                atlas_run_id=atlas_run.id,
                region_key=region_key,
                subregion_key=subregion_key,
                source_item_ids=representative_ids,
                filters=filters,
            ),
            bridges=bridge_total,
            long_tail=long_tail_total,
        ),
        active_filters=filters,
    )


def _get_latest_published_run(session: Session) -> AtlasRun | None:
    return session.scalar(
        select(AtlasRun)
        .where(
            AtlasRun.atlas_key == ATLAS_KEY,
            AtlasRun.published_at.is_not(None),
        )
        .order_by(AtlasRun.published_at.desc(), AtlasRun.id.desc())
    )


def _load_region_row(
    session: Session,
    *,
    atlas_run_id: int,
    region_key: str,
) -> AtlasRegion | None:
    return session.scalar(
        select(AtlasRegion).where(
            AtlasRegion.atlas_run_id == atlas_run_id,
            AtlasRegion.region_key == region_key,
        )
    )


def _load_regions(
    session: Session,
    *,
    atlas_run_id: int,
    level: int | None = None,
    parent_region_key: str | None = None,
) -> list[AtlasRegionView]:
    query = select(AtlasRegion).where(AtlasRegion.atlas_run_id == atlas_run_id)
    if level is not None:
        query = query.where(AtlasRegion.level == level)
    if parent_region_key is None and level is None:
        query = query.where(AtlasRegion.parent_region_key.is_(None))
    elif parent_region_key is not None:
        query = query.where(AtlasRegion.parent_region_key == parent_region_key)
    rows = session.scalars(
        query.order_by(
            AtlasRegion.level.asc(),
            AtlasRegion.region_key.asc(),
        )
    ).all()
    return [_atlas_region_view(row) for row in rows]


def _load_edges(
    session: Session,
    *,
    atlas_run_id: int,
    region_keys: list[str],
) -> list[AtlasEdgeView]:
    if not region_keys:
        return []
    rows = session.scalars(
        select(AtlasEdge)
        .where(
            AtlasEdge.atlas_run_id == atlas_run_id,
            AtlasEdge.source_region_key.in_(region_keys),
            AtlasEdge.target_region_key.in_(region_keys),
        )
        .order_by(
            AtlasEdge.edge_type.asc(),
            AtlasEdge.source_region_key.asc(),
            AtlasEdge.target_region_key.asc(),
        )
    ).all()
    return [
        AtlasEdgeView(
            source_region_key=row.source_region_key,
            target_region_key=row.target_region_key,
            weight=row.weight,
            edge_type=row.edge_type,
        )
        for row in rows
    ]


def _build_region_overlays(
    session: Session,
    *,
    atlas_run_id: int,
    filters: ScreenshotReadFilters,
    group_by: str,
    region_key: str | None = None,
) -> dict[str, AtlasOverlay]:
    if group_by == "region":
        group_column = AtlasItem.region_key
    elif group_by == "subregion":
        group_column = AtlasItem.subregion_key
    else:
        raise ValueError(f"unsupported atlas overlay grouping: {group_by}")

    query = (
        select(group_column.label("group_key"), func.count(AtlasItem.id))
        .select_from(AtlasItem)
        .join(SourceItem, SourceItem.id == AtlasItem.source_item_id)
        .where(AtlasItem.atlas_run_id == atlas_run_id)
    )
    if region_key is not None:
        query = query.where(AtlasItem.region_key == region_key)
    if group_by == "subregion":
        query = query.where(group_column.is_not(None))
    for clause in build_screenshot_filter_clauses(filters):
        query = query.where(clause)

    rows = session.execute(query.group_by(group_column)).all()
    return {
        str(group_key): AtlasOverlay(match_count=int(match_count))
        for group_key, match_count in rows
        if group_key is not None
    }


def _attach_region_overlays(
    regions: list[AtlasRegionView],
    overlays: dict[str, AtlasOverlay],
) -> list[AtlasRegionView]:
    return [
        AtlasRegionView(
            atlas_run_id=region.atlas_run_id,
            region_key=region.region_key,
            parent_region_key=region.parent_region_key,
            level=region.level,
            title=region.title,
            x=region.x,
            y=region.y,
            label_x=region.label_x,
            label_y=region.label_y,
            region_shape=region.region_shape,
            item_count=region.item_count,
            top_labels=region.top_labels,
            top_apps=region.top_apps,
            top_people=region.top_people,
            top_entities=region.top_entities,
            time_start=region.time_start,
            time_end=region.time_end,
            representatives=region.representatives,
            bridge_neighbors=region.bridge_neighbors,
            cohesion_score=region.cohesion_score,
            overlay=overlays.get(region.region_key, AtlasOverlay()),
        )
        for region in regions
    ]


def _load_items_for_source_item_ids(
    session: Session,
    *,
    atlas_run_id: int,
    region_key: str,
    subregion_key: str | None,
    source_item_ids: list[int],
    filters: ScreenshotReadFilters,
    limit: int | None = None,
) -> list[AtlasItemView]:
    if not source_item_ids:
        return []

    query = _base_item_query(
        atlas_run_id=atlas_run_id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        source_item_ids=source_item_ids,
    ).order_by(
        AtlasItem.representative_rank.is_(None).asc(),
        AtlasItem.representative_rank.asc(),
        AtlasItem.source_item_id.asc(),
    )
    if limit is not None:
        query = query.limit(limit)

    rows = session.scalars(query).all()
    items_by_source_item_id = {
        row.source_item_id: _atlas_item_view(row)
        for row in rows
    }
    ordered_items = [
        items_by_source_item_id[source_item_id]
        for source_item_id in source_item_ids
        if source_item_id in items_by_source_item_id
    ]
    if limit is not None:
        return ordered_items[:limit]
    return ordered_items


def _load_items(
    session: Session,
    *,
    atlas_run_id: int,
    region_key: str,
    subregion_key: str | None,
    filters: ScreenshotReadFilters,
    bridge_only: bool = False,
    long_tail_only: bool = False,
    exclude_source_item_ids: set[int] | None = None,
    limit: int,
    offset: int,
    sort: str,
) -> list[AtlasItemView]:
    query = _base_item_query(
        atlas_run_id=atlas_run_id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        bridge_only=bridge_only,
        long_tail_only=long_tail_only,
        exclude_source_item_ids=exclude_source_item_ids,
    )
    query = query.order_by(*_item_order(sort))
    rows = session.scalars(query.offset(offset).limit(limit)).all()
    return [_atlas_item_view(row) for row in rows]


def _count_items(
    session: Session,
    *,
    atlas_run_id: int,
    region_key: str,
    subregion_key: str | None,
    filters: ScreenshotReadFilters,
    bridge_only: bool = False,
    long_tail_only: bool = False,
    exclude_source_item_ids: set[int] | None = None,
) -> int:
    subquery = _base_item_query(
        atlas_run_id=atlas_run_id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        bridge_only=bridge_only,
        long_tail_only=long_tail_only,
        exclude_source_item_ids=exclude_source_item_ids,
    ).with_only_columns(AtlasItem.id)
    return int(session.scalar(select(func.count()).select_from(subquery.subquery())) or 0)


def _count_items_for_source_item_ids(
    session: Session,
    *,
    atlas_run_id: int,
    region_key: str,
    subregion_key: str | None,
    source_item_ids: list[int],
    filters: ScreenshotReadFilters,
) -> int:
    if not source_item_ids:
        return 0
    subquery = _base_item_query(
        atlas_run_id=atlas_run_id,
        region_key=region_key,
        subregion_key=subregion_key,
        filters=filters,
        source_item_ids=source_item_ids,
    ).with_only_columns(AtlasItem.id)
    return int(session.scalar(select(func.count()).select_from(subquery.subquery())) or 0)


def _base_item_query(
    *,
    atlas_run_id: int,
    region_key: str,
    subregion_key: str | None,
    filters: ScreenshotReadFilters,
    source_item_ids: list[int] | None = None,
    bridge_only: bool = False,
    long_tail_only: bool = False,
    exclude_source_item_ids: set[int] | None = None,
):
    query = (
        select(AtlasItem)
        .join(SourceItem, SourceItem.id == AtlasItem.source_item_id)
        .where(
            AtlasItem.atlas_run_id == atlas_run_id,
            AtlasItem.region_key == region_key,
        )
    )
    if subregion_key is not None:
        query = query.where(AtlasItem.subregion_key == subregion_key)
    if source_item_ids is not None:
        query = query.where(AtlasItem.source_item_id.in_(source_item_ids))
    if bridge_only:
        query = query.where(AtlasItem.is_bridge.is_(True))
    if long_tail_only:
        query = query.where(
            AtlasItem.is_representative.is_(False),
            AtlasItem.is_bridge.is_(False),
        )
    if exclude_source_item_ids:
        query = query.where(AtlasItem.source_item_id.not_in(sorted(exclude_source_item_ids)))
    for clause in build_screenshot_filter_clauses(filters):
        query = query.where(clause)
    return query


def _representative_source_item_ids(region_row: AtlasRegion) -> list[int]:
    payload = _json_value(region_row.representatives_json, default=[])
    if not isinstance(payload, list):
        return []

    ranked_source_item_ids: list[tuple[int, int]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        source_item_id = entry.get("source_item_id")
        rank = entry.get("rank")
        if isinstance(source_item_id, int) and isinstance(rank, int):
            ranked_source_item_ids.append((rank, source_item_id))
    return [source_item_id for rank, source_item_id in sorted(ranked_source_item_ids)]


def _atlas_run_view(row: AtlasRun) -> AtlasRunView:
    clustering_params = _json_value(row.clustering_params_json, default={})
    if not isinstance(clustering_params, dict):
        clustering_params = {}
    return AtlasRunView(
        atlas_run_id=row.id,
        atlas_key=row.atlas_key,
        status=row.status,
        source_count=row.source_count,
        source_snapshot_id=row.source_snapshot_id,
        corpus_hash=row.corpus_hash,
        embedding_type=row.embedding_type,
        embedding_model=row.embedding_model,
        embedding_version=row.embedding_version,
        clustering_method=row.clustering_method,
        clustering_params=clustering_params,
        random_seed=row.random_seed,
        layout_version=row.layout_version,
        generated_at=row.created_at,
        completed_at=row.completed_at,
        published_at=row.published_at,
    )


def _atlas_region_view(
    row: AtlasRegion,
    *,
    overlay: AtlasOverlay | None = None,
) -> AtlasRegionView:
    region_shape = _json_value(row.region_shape_json, default=_EMPTY_REGION_SHAPE)
    if not isinstance(region_shape, dict):
        region_shape = dict(_EMPTY_REGION_SHAPE)
    return AtlasRegionView(
        atlas_run_id=row.atlas_run_id,
        region_key=row.region_key,
        parent_region_key=row.parent_region_key,
        level=row.level,
        title=row.title,
        x=row.x,
        y=row.y,
        label_x=row.label_x,
        label_y=row.label_y,
        region_shape=region_shape,
        item_count=row.item_count,
        top_labels=_json_string_list(row.top_labels_json),
        top_apps=_json_string_list(row.top_apps_json),
        top_people=_json_string_list(row.top_people_json),
        top_entities=_json_string_list(row.top_entities_json),
        time_start=row.time_start,
        time_end=row.time_end,
        representatives=[
            AtlasRepresentativeRef(rank=entry["rank"], source_item_id=entry["source_item_id"])
            for entry in _json_representative_entries(row.representatives_json)
        ],
        bridge_neighbors=[
            AtlasBridgeNeighbor(
                edge_type=entry["edge_type"],
                region_key=entry["region_key"],
                weight=float(entry["weight"]),
            )
            for entry in _json_bridge_neighbor_entries(row.bridge_neighbors_json)
        ],
        cohesion_score=row.cohesion_score,
        overlay=overlay or AtlasOverlay(),
    )


def _atlas_item_view(row: AtlasItem) -> AtlasItemView:
    return AtlasItemView(
        source_item_id=row.source_item_id,
        region_key=row.region_key,
        subregion_key=row.subregion_key,
        x=row.x,
        y=row.y,
        semantic_summary=row.semantic_summary,
        app_hint=row.app_hint,
        observed_at=row.observed_at,
        object_refs=_json_string_list(row.object_refs_json),
        is_representative=bool(row.is_representative),
        representative_rank=row.representative_rank,
        is_bridge=bool(row.is_bridge),
        bridge_type=row.bridge_type,
        secondary_region_key=row.secondary_region_key,
        bridge_score=row.bridge_score,
        screenshot_detail_url=row.screenshot_detail_url,
    )


def _json_string_list(raw_value: str | None) -> list[str]:
    payload = _json_value(raw_value, default=[])
    if not isinstance(payload, list):
        return []
    return [str(entry) for entry in payload]


def _json_representative_entries(raw_value: str | None) -> list[dict[str, int]]:
    payload = _json_value(raw_value, default=[])
    if not isinstance(payload, list):
        return []

    entries: list[dict[str, int]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        source_item_id = entry.get("source_item_id")
        rank = entry.get("rank")
        if isinstance(source_item_id, int) and isinstance(rank, int):
            entries.append({"source_item_id": source_item_id, "rank": rank})
    return sorted(entries, key=lambda item: (item["rank"], item["source_item_id"]))


def _json_bridge_neighbor_entries(raw_value: str | None) -> list[dict[str, object]]:
    payload = _json_value(raw_value, default=[])
    if not isinstance(payload, list):
        return []

    entries: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        edge_type = entry.get("edge_type")
        region_key = entry.get("region_key")
        weight = entry.get("weight")
        if isinstance(edge_type, str) and isinstance(region_key, str) and weight is not None:
            entries.append(
                {
                    "edge_type": edge_type,
                    "region_key": region_key,
                    "weight": float(weight),
                }
            )
    return entries


def _json_value(raw_value: str | None, *, default: object) -> object:
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return default


def _item_order(sort: str):
    if sort == "bridge_score_desc":
        return (
            AtlasItem.bridge_score.desc(),
            AtlasItem.source_item_id.asc(),
        )
    if sort == "observed_at_asc":
        return (
            AtlasItem.observed_at.is_(None).asc(),
            AtlasItem.observed_at.asc(),
            AtlasItem.source_item_id.asc(),
        )
    if sort == "source_item_id_asc":
        return (AtlasItem.source_item_id.asc(),)
    if sort == "source_item_id_desc":
        return (AtlasItem.source_item_id.desc(),)
    if sort != "observed_at_desc":
        raise ValueError(f"unsupported atlas evidence sort: {sort}")
    return (
        AtlasItem.observed_at.is_(None).asc(),
        AtlasItem.observed_at.desc(),
        AtlasItem.source_item_id.desc(),
    )
