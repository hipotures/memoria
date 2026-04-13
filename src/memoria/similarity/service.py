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
_MAX_METADATA_VALUES = 5
_MAX_REPRESENTATIVE_SOURCE_ITEM_IDS = 8
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
    label: str
    canonical_title: str
    duplicate_title_count: int
    x: float
    y: float
    label_x: float
    label_y: float
    size: float
    item_count: int
    degree: int
    label_priority: float
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
    edge_type: str
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
    graph_kind: str
    edge_scope: str
    default_label_limit: int | None = None


@dataclass(frozen=True, slots=True)
class _RegionSliceStats:
    item_count: int
    dominant_screen_category: str
    top_labels: list[str]
    top_apps: list[str]
    top_entities: list[str]
    representative_source_item_ids: list[int]


@dataclass(frozen=True, slots=True)
class _RawSimilarityGraphNode:
    region_key: str
    title: str
    x: float
    y: float
    label_x: float
    label_y: float
    size: float
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
            graph_kind="region_similarity",
            edge_scope="atlas_snapshot",
        )

    raw_nodes = _load_similarity_nodes(
        session,
        atlas_run_id=atlas_run.id,
        filters=resolved_filters,
    )
    region_keys = {node.region_key for node in raw_nodes}
    edges = _load_similarity_edges(
        session,
        atlas_run_id=atlas_run.id,
        region_keys=region_keys,
        min_edge_weight=resolved_filters.min_edge_weight,
    )
    nodes = _decorate_similarity_nodes(raw_nodes, edges)
    return SimilarityGraph(
        run=_build_run_view(atlas_run),
        nodes=nodes,
        edges=edges,
        legend=_build_legend(nodes),
        filters=resolved_filters,
        graph_kind="region_similarity",
        edge_scope="atlas_snapshot",
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
) -> list[_RawSimilarityGraphNode]:
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
        _RawSimilarityGraphNode(
            region_key=row.region_key,
            title=row.title,
            x=row.x,
            y=row.y,
            label_x=row.label_x,
            label_y=row.label_y,
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
    representative_source_item_ids = representative_source_item_ids[
        :_MAX_REPRESENTATIVE_SOURCE_ITEM_IDS
    ]

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
            edge_type=row.edge_type,
            reason=row.edge_type,
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


def _decorate_similarity_nodes(
    raw_nodes: list[_RawSimilarityGraphNode],
    edges: list[SimilarityGraphEdge],
) -> list[SimilarityGraphNode]:
    degree_by_region = _compute_node_degree(edges)
    canonical_titles = {
        node.region_key: _canonical_title(node.title, node.region_key) for node in raw_nodes
    }
    duplicate_title_counts = Counter(canonical_titles.values())
    labels_by_region = _build_node_labels(
        raw_nodes=raw_nodes,
        canonical_titles=canonical_titles,
        duplicate_title_counts=duplicate_title_counts,
    )

    return [
        SimilarityGraphNode(
            region_key=node.region_key,
            title=node.title,
            label=labels_by_region[node.region_key],
            canonical_title=canonical_titles[node.region_key],
            duplicate_title_count=duplicate_title_counts[canonical_titles[node.region_key]],
            x=node.x,
            y=node.y,
            label_x=node.label_x,
            label_y=node.label_y,
            size=node.size,
            item_count=node.item_count,
            degree=degree_by_region.get(node.region_key, 0),
            label_priority=_compute_label_priority(
                item_count=node.item_count,
                degree=degree_by_region.get(node.region_key, 0),
            ),
            dominant_screen_category=node.dominant_screen_category,
            top_labels=node.top_labels,
            top_apps=node.top_apps,
            top_entities=node.top_entities,
            is_labeled=bool(node.title.strip()),
            representative_source_item_ids=node.representative_source_item_ids,
        )
        for node in raw_nodes
    ]


def _build_node_labels(
    *,
    raw_nodes: list[_RawSimilarityGraphNode],
    canonical_titles: dict[str, str],
    duplicate_title_counts: Counter[str],
) -> dict[str, str]:
    grouped_nodes: dict[str, list[_RawSimilarityGraphNode]] = {}
    for node in raw_nodes:
        grouped_nodes.setdefault(canonical_titles[node.region_key], []).append(node)

    labels: dict[str, str] = {}
    for canonical_title, nodes in grouped_nodes.items():
        if duplicate_title_counts[canonical_title] <= 1:
            node = nodes[0]
            labels[node.region_key] = _display_title(node.title, node.region_key)
            continue

        unresolved = {node.region_key: node for node in nodes}
        used_labels: set[str] = set(labels.values())
        for candidate_index in range(3):
            candidate_counts: Counter[str] = Counter()
            for node in unresolved.values():
                candidate = _label_candidate(
                    node,
                    candidate_index=candidate_index,
                )
                if candidate is not None:
                    candidate_counts[candidate] += 1

            resolved_region_keys: list[str] = []
            for region_key, node in unresolved.items():
                candidate = _label_candidate(
                    node,
                    candidate_index=candidate_index,
                )
                if candidate is None or candidate_counts[candidate] != 1 or candidate in used_labels:
                    continue
                labels[region_key] = candidate
                used_labels.add(candidate)
                resolved_region_keys.append(region_key)

            for region_key in resolved_region_keys:
                unresolved.pop(region_key)

        for region_key, node in sorted(unresolved.items()):
            labels[region_key] = _label_candidate(node, candidate_index=2) or _display_title(
                node.title,
                node.region_key,
            )

    return _ensure_globally_unique_labels(raw_nodes=raw_nodes, candidate_labels=labels)


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


def _normalize_title(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _compute_node_degree(edges: list[SimilarityGraphEdge]) -> dict[str, int]:
    degree: Counter[str] = Counter()
    for edge in edges:
        degree[edge.source_region_key] += 1
        degree[edge.target_region_key] += 1
    return dict(degree)


def _compute_label_priority(*, item_count: int, degree: int) -> float:
    return float(item_count + 3 * degree)


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
    return [
        source_item_id
        for rank, source_item_id in sorted(ranked_entries, key=lambda entry: (entry[0], entry[1]))[
            :_MAX_REPRESENTATIVE_SOURCE_ITEM_IDS
        ]
    ]


def _canonical_title(title: str, region_key: str) -> str:
    normalized = _normalize_title(title)
    return normalized or _normalize_title(region_key)


def _display_title(title: str, region_key: str) -> str:
    stripped = title.strip()
    return stripped or region_key


def _label_candidate(
    node: _RawSimilarityGraphNode,
    *,
    candidate_index: int,
) -> str | None:
    title = _display_title(node.title, node.region_key)
    if candidate_index == 0:
        top_app = node.top_apps[0].strip() if node.top_apps else ""
        if top_app:
            return f"{title} · {top_app}"
        return None
    if candidate_index == 1:
        return f"{title} · {node.item_count}"
    if candidate_index == 2:
        return f"{title} · {node.region_key[-6:]}"
    return None


def _clean_region_key_label(node: _RawSimilarityGraphNode) -> str:
    return f"{_display_title(node.title, node.region_key)} · {node.region_key}"


def _ensure_globally_unique_labels(
    *,
    raw_nodes: list[_RawSimilarityGraphNode],
    candidate_labels: dict[str, str],
) -> dict[str, str]:
    unique_labels: dict[str, str] = {}
    used_labels: set[str] = set()

    for node in raw_nodes:
        base_label = candidate_labels.get(node.region_key, _display_title(node.title, node.region_key))
        final_label = _make_globally_unique_label(
            preferred_label=base_label,
            clean_fallback_label=_clean_region_key_label(node),
            used_labels=used_labels,
        )
        unique_labels[node.region_key] = final_label
        used_labels.add(final_label)

    return unique_labels


def _make_globally_unique_label(
    *,
    preferred_label: str,
    clean_fallback_label: str,
    used_labels: set[str],
) -> str:
    if preferred_label not in used_labels:
        return preferred_label
    if clean_fallback_label not in used_labels:
        return clean_fallback_label

    suffix = 2
    while True:
        candidate = f"{clean_fallback_label} #{suffix}"
        if candidate not in used_labels:
            return candidate
        suffix += 1


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
