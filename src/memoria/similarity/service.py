from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.filters import AtlasFilters
from memoria.atlas.service import _get_latest_published_run
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun

_DEFAULT_CATEGORY = "unknown"
_REASON_SHARED_TOPIC_TASK_SIGNATURE = "shared_topic_task_signature"
_CATEGORY_COLORS = {
    "chat": "#6EC5FF",
    "finance": "#F4B942",
    "notes": "#A78BFA",
    "social": "#2EC4B6",
    "unknown": "#94A3B8",
}


@dataclass(frozen=True, slots=True)
class SimilarityGraphFilters(AtlasFilters):
    min_cluster_size: int = 1
    min_edge_weight: float = 0.0


@dataclass(frozen=True, slots=True)
class SimilarityGraphRun:
    atlas_run_id: int
    atlas_key: str
    generated_at: datetime
    source_count: int


@dataclass(frozen=True, slots=True)
class SimilarityGraphNode:
    region_key: str
    title: str
    x: float
    y: float
    size: float
    item_count: int
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    is_labeled: bool
    representative_source_item_ids: list[int]


@dataclass(frozen=True, slots=True)
class SimilarityGraphEdge:
    source_region_key: str
    target_region_key: str
    weight: float
    support: int
    reason: str


@dataclass(frozen=True, slots=True)
class SimilarityGraphLegendEntry:
    category: str
    color: str
    count: int


@dataclass(frozen=True, slots=True)
class SimilarityGraph:
    run: SimilarityGraphRun | None
    nodes: list[SimilarityGraphNode]
    edges: list[SimilarityGraphEdge]
    legend: list[SimilarityGraphLegendEntry]
    filters: SimilarityGraphFilters


def get_similarity_graph(
    session: Session,
    *,
    filters: SimilarityGraphFilters | None = None,
    min_cluster_size: int | None = None,
    min_edge_weight: float | None = None,
) -> SimilarityGraph:
    resolved_filters = _resolve_filters(
        filters=filters,
        min_cluster_size=min_cluster_size,
        min_edge_weight=min_edge_weight,
    )

    atlas_run = _get_latest_published_run(session)
    if atlas_run is None:
        return SimilarityGraph(
            run=None,
            nodes=[],
            edges=[],
            legend=[],
            filters=resolved_filters,
        )

    nodes = _load_similarity_nodes(
        session,
        atlas_run_id=atlas_run.id,
        filters=resolved_filters,
    )
    region_keys = {node.region_key for node in nodes}
    edges = _load_similarity_edges(
        session,
        atlas_run_id=atlas_run.id,
        region_keys=region_keys,
        min_edge_weight=resolved_filters.min_edge_weight,
    )
    return SimilarityGraph(
        run=_build_run_view(atlas_run),
        nodes=nodes,
        edges=edges,
        legend=_build_legend(nodes),
        filters=resolved_filters,
    )


def _resolve_filters(
    *,
    filters: SimilarityGraphFilters | None,
    min_cluster_size: int | None,
    min_edge_weight: float | None,
) -> SimilarityGraphFilters:
    if filters is None:
        return SimilarityGraphFilters(
            min_cluster_size=max(1, min_cluster_size or 1),
            min_edge_weight=max(0.0, min_edge_weight or 0.0),
        )
    return SimilarityGraphFilters(
        connector_instance_id=filters.connector_instance_id,
        app_hint=filters.app_hint,
        screen_category=filters.screen_category,
        has_knowledge=filters.has_knowledge,
        observed_from=filters.observed_from,
        observed_to=filters.observed_to,
        search_query=filters.search_query,
        min_cluster_size=max(1, min_cluster_size or filters.min_cluster_size),
        min_edge_weight=max(0.0, min_edge_weight or filters.min_edge_weight),
    )


def _load_similarity_nodes(
    session: Session,
    *,
    atlas_run_id: int,
    filters: SimilarityGraphFilters,
) -> list[SimilarityGraphNode]:
    rows = session.scalars(
        select(AtlasRegion)
        .where(
            AtlasRegion.atlas_run_id == atlas_run_id,
            AtlasRegion.level == 0,
            AtlasRegion.parent_region_key.is_(None),
            AtlasRegion.item_count >= filters.min_cluster_size,
        )
        .order_by(AtlasRegion.region_key.asc())
    ).all()

    return [
        SimilarityGraphNode(
            region_key=row.region_key,
            title=row.title,
            x=row.x,
            y=row.y,
            size=_node_size(row.item_count),
            item_count=row.item_count,
            dominant_screen_category=_dominant_screen_category(session, atlas_run_id, row.region_key),
            top_labels=_json_string_list(row.top_labels_json),
            top_apps=_json_string_list(row.top_apps_json),
            top_entities=_json_string_list(row.top_entities_json),
            is_labeled=bool(row.title.strip()),
            representative_source_item_ids=_representative_source_item_ids(row.representatives_json),
        )
        for row in rows
    ]


def _load_similarity_edges(
    session: Session,
    *,
    atlas_run_id: int,
    region_keys: set[str],
    min_edge_weight: float,
) -> list[SimilarityGraphEdge]:
    if not region_keys:
        return []

    rows = session.scalars(
        select(AtlasEdge)
        .where(
            AtlasEdge.atlas_run_id == atlas_run_id,
            AtlasEdge.edge_type == "semantic_similarity",
            AtlasEdge.source_region_key.in_(region_keys),
            AtlasEdge.target_region_key.in_(region_keys),
            AtlasEdge.weight >= min_edge_weight,
        )
        .order_by(
            AtlasEdge.source_region_key.asc(),
            AtlasEdge.target_region_key.asc(),
        )
    ).all()

    return [
        SimilarityGraphEdge(
            source_region_key=row.source_region_key,
            target_region_key=row.target_region_key,
            weight=row.weight,
            support=1,
            reason=_REASON_SHARED_TOPIC_TASK_SIGNATURE,
        )
        for row in rows
    ]


def _build_run_view(row: AtlasRun) -> SimilarityGraphRun:
    return SimilarityGraphRun(
        atlas_run_id=row.id,
        atlas_key=row.atlas_key,
        generated_at=row.created_at,
        source_count=row.source_count,
    )


def _build_legend(nodes: list[SimilarityGraphNode]) -> list[SimilarityGraphLegendEntry]:
    counts: Counter[str] = Counter()
    ordered_categories: list[str] = []
    for node in nodes:
        category = node.dominant_screen_category or _DEFAULT_CATEGORY
        if category not in counts:
            ordered_categories.append(category)
        counts[category] += 1

    return [
        SimilarityGraphLegendEntry(
            category=category,
            color=_category_color(category),
            count=counts[category],
        )
        for category in ordered_categories
    ]


def _dominant_screen_category(session: Session, atlas_run_id: int, region_key: str) -> str:
    categories = session.scalars(
        select(AtlasItem.screen_category)
        .where(
            AtlasItem.atlas_run_id == atlas_run_id,
            AtlasItem.region_key == region_key,
        )
        .order_by(AtlasItem.source_item_id.asc())
    ).all()

    if not categories:
        return _DEFAULT_CATEGORY

    counts = Counter(category or _DEFAULT_CATEGORY for category in categories)
    return sorted(counts.items(), key=lambda entry: (-entry[1], entry[0]))[0][0]


def _node_size(item_count: int) -> float:
    return round(10.0 + (math.sqrt(max(item_count, 1)) * 4.0), 3)


def _representative_source_item_ids(raw_value: str | None) -> list[int]:
    payload = _json_value(raw_value, default=[])
    if not isinstance(payload, list):
        return []

    ranked_entries: list[tuple[int, int]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        rank = entry.get("rank")
        source_item_id = entry.get("source_item_id")
        if isinstance(rank, int) and isinstance(source_item_id, int):
            ranked_entries.append((rank, source_item_id))
    return [source_item_id for rank, source_item_id in sorted(ranked_entries)]


def _json_string_list(raw_value: str | None) -> list[str]:
    payload = _json_value(raw_value, default=[])
    if not isinstance(payload, list):
        return []
    return [str(entry) for entry in payload]


def _json_value(raw_value: str | None, *, default: object) -> object:
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return default


def _category_color(category: str) -> str:
    if category in _CATEGORY_COLORS:
        return _CATEGORY_COLORS[category]
    palette = ("#6EC5FF", "#2EC4B6", "#F4B942", "#FB7185", "#A78BFA", "#34D399")
    return palette[sum(ord(char) for char in category) % len(palette)]
