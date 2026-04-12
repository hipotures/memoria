from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.filters import AtlasFilters
from memoria.atlas.service import _build_atlas_filter_clauses
from memoria.atlas.service import _get_latest_published_run
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun

_DEFAULT_CATEGORY = "unknown"
_REASON_SHARED_TOPIC_TASK_SIGNATURE = "shared_topic_task_signature"
_MAX_METADATA_VALUES = 5
_SUMMARY_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
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


@dataclass(frozen=True, slots=True)
class _RegionSliceStats:
    item_count: int
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    representative_source_item_ids: list[int]


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
        filters=resolved_filters,
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
    resolved_min_cluster_size = min_cluster_size if min_cluster_size is not None else (
        filters.min_cluster_size if filters is not None else 1
    )
    resolved_min_edge_weight = min_edge_weight if min_edge_weight is not None else (
        filters.min_edge_weight if filters is not None else 0.0
    )
    if filters is None:
        return SimilarityGraphFilters(
            min_cluster_size=max(0, resolved_min_cluster_size),
            min_edge_weight=max(0.0, resolved_min_edge_weight),
        )
    return SimilarityGraphFilters(
        connector_instance_id=filters.connector_instance_id,
        app_hint=filters.app_hint,
        screen_category=filters.screen_category,
        has_knowledge=filters.has_knowledge,
        observed_from=filters.observed_from,
        observed_to=filters.observed_to,
        search_query=filters.search_query,
        min_cluster_size=max(0, resolved_min_cluster_size),
        min_edge_weight=max(0.0, resolved_min_edge_weight),
    )


def _load_similarity_nodes(
    session: Session,
    *,
    atlas_run_id: int,
    filters: SimilarityGraphFilters,
) -> list[SimilarityGraphNode]:
    use_snapshot_metadata = not _has_non_threshold_item_filters(filters)
    region_slice_stats = _load_region_slice_stats(
        session,
        atlas_run_id=atlas_run_id,
        filters=filters,
    )
    included_region_keys = [
        region_key
        for region_key, stats in sorted(region_slice_stats.items())
        if stats.item_count >= filters.min_cluster_size
    ]
    if not included_region_keys:
        return []

    rows = session.scalars(
        select(AtlasRegion)
        .where(
            AtlasRegion.atlas_run_id == atlas_run_id,
            AtlasRegion.level == 0,
            AtlasRegion.parent_region_key.is_(None),
            AtlasRegion.region_key.in_(included_region_keys),
        )
        .order_by(AtlasRegion.region_key.asc())
    ).all()

    return [
        SimilarityGraphNode(
            region_key=row.region_key,
            title=row.title,
            x=row.x,
            y=row.y,
            size=_node_size(region_slice_stats[row.region_key].item_count),
            item_count=region_slice_stats[row.region_key].item_count,
            dominant_screen_category=region_slice_stats[row.region_key].dominant_screen_category,
            top_labels=(
                _json_string_list(row.top_labels_json)
                if use_snapshot_metadata
                else region_slice_stats[row.region_key].top_labels
            ),
            top_apps=(
                _json_string_list(row.top_apps_json)
                if use_snapshot_metadata
                else region_slice_stats[row.region_key].top_apps
            ),
            top_entities=(
                _json_string_list(row.top_entities_json)
                if use_snapshot_metadata
                else region_slice_stats[row.region_key].top_entities
            ),
            is_labeled=bool(row.title.strip()),
            representative_source_item_ids=(
                _snapshot_representative_source_item_ids(row.representatives_json)
                if use_snapshot_metadata
                else region_slice_stats[row.region_key].representative_source_item_ids
            ),
        )
        for row in rows
    ]


def _load_region_slice_stats(
    session: Session,
    *,
    atlas_run_id: int,
    filters: SimilarityGraphFilters,
) -> dict[str, _RegionSliceStats]:
    rows = _load_filtered_items(
        session,
        atlas_run_id=atlas_run_id,
        filters=filters,
    )
    grouped_rows: dict[str, list[AtlasItem]] = {}
    for row in rows:
        if row.region_key is None:
            continue
        grouped_rows.setdefault(row.region_key, []).append(row)

    return {
        region_key: _build_region_slice_stats(region_rows)
        for region_key, region_rows in grouped_rows.items()
    }


def _load_filtered_items(
    session: Session,
    *,
    atlas_run_id: int,
    filters: SimilarityGraphFilters,
) -> list[AtlasItem]:
    query = (
        select(AtlasItem)
        .where(
            AtlasItem.atlas_run_id == atlas_run_id,
            AtlasItem.region_key.is_not(None),
        )
        .order_by(
            AtlasItem.region_key.asc(),
            AtlasItem.source_item_id.asc(),
        )
    )
    for clause in _build_atlas_filter_clauses(filters):
        query = query.where(clause)
    return session.scalars(query).all()


def _build_region_slice_stats(rows: list[AtlasItem]) -> _RegionSliceStats:
    category_counts: Counter[str] = Counter()
    app_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    entity_counts: Counter[str] = Counter()
    representative_entries: list[tuple[int, int]] = []
    fallback_representatives: list[int] = []

    for row in rows:
        category_counts[(row.screen_category or _DEFAULT_CATEGORY)] += 1
        if row.app_hint:
            app_counts[row.app_hint] += 1
        label_counts.update(_label_values_for_item(row))
        entity_counts.update(_entity_values_for_item(row))
        if row.is_representative:
            if row.representative_rank is not None:
                representative_entries.append((row.representative_rank, row.source_item_id))
            else:
                fallback_representatives.append(row.source_item_id)

    dominant_screen_category = _DEFAULT_CATEGORY
    if category_counts:
        dominant_screen_category = sorted(
            category_counts.items(),
            key=lambda entry: (-entry[1], entry[0]),
        )[0][0]

    representative_source_item_ids = [
        source_item_id
        for rank, source_item_id in sorted(representative_entries, key=lambda entry: (entry[0], entry[1]))
    ]
    representative_source_item_ids.extend(sorted(fallback_representatives))

    return _RegionSliceStats(
        item_count=len(rows),
        dominant_screen_category=dominant_screen_category,
        top_labels=_top_counter_values(label_counts),
        top_apps=_top_counter_values(app_counts),
        top_entities=_top_counter_values(entity_counts),
        representative_source_item_ids=representative_source_item_ids,
    )


def _load_similarity_edges(
    session: Session,
    *,
    atlas_run_id: int,
    region_keys: set[str],
    filters: SimilarityGraphFilters,
    min_edge_weight: float,
) -> list[SimilarityGraphEdge]:
    if not region_keys or _has_non_threshold_item_filters(filters):
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


def _node_size(item_count: int) -> float:
    return round(10.0 + (math.sqrt(max(item_count, 1)) * 4.0), 3)


def _snapshot_representative_source_item_ids(raw_value: str | None) -> list[int]:
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
    return [source_item_id for rank, source_item_id in sorted(ranked_entries, key=lambda entry: (entry[0], entry[1]))]


def _label_values_for_item(row: AtlasItem) -> list[str]:
    labels: set[str] = set()
    for object_ref in _json_string_list(row.object_refs_json):
        prefix, separator, raw_value = object_ref.partition(":")
        candidate = _normalize_metadata_value(raw_value if separator else object_ref)
        if not candidate:
            continue
        if separator and prefix in {"entity", "person"}:
            continue
        labels.add(candidate)
    if not labels and row.semantic_summary:
        labels.update(_summary_tokens(row.semantic_summary))
    return sorted(labels)


def _entity_values_for_item(row: AtlasItem) -> list[str]:
    entities: set[str] = set()
    for object_ref in _json_string_list(row.object_refs_json):
        prefix, separator, raw_value = object_ref.partition(":")
        if not separator or prefix not in {"entity", "person"}:
            continue
        candidate = _normalize_metadata_value(raw_value)
        if candidate:
            entities.add(candidate)
    return sorted(entities)


def _summary_tokens(text: str) -> list[str]:
    return sorted({match.group(0).lower() for match in _SUMMARY_TOKEN_PATTERN.finditer(text)})


def _normalize_metadata_value(value: str) -> str | None:
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized or None


def _top_counter_values(counter: Counter[str]) -> list[str]:
    return [
        value
        for value, count in sorted(counter.items(), key=lambda entry: (-entry[1], entry[0]))[
            :_MAX_METADATA_VALUES
        ]
    ]


def _has_non_threshold_item_filters(filters: SimilarityGraphFilters) -> bool:
    return any(
        value is not None
        for value in (
            filters.connector_instance_id,
            filters.app_hint,
            filters.screen_category,
            filters.has_knowledge,
            filters.observed_from,
            filters.observed_to,
            filters.search_query,
        )
    )


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
