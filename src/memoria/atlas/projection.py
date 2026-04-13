from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from itertools import combinations
from math import dist
from typing import Sequence

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.atlas.contracts import AtlasCandidateItem
from memoria.atlas.contracts import BridgeClassification
from memoria.atlas.contracts import PriorRegionIdentity
from memoria.domain.models import AssetInterpretation
from memoria.domain.models import Embedding
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import PipelineRun
from memoria.domain.models import SemanticCluster
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourceItem
from memoria.search.embeddings import embed_text

ATLAS_KEY = "screenshots_atlas_v1"
ATLAS_EMBEDDING_TYPE = "screenshot_semantic_text"
ATLAS_CLUSTERING_METHOD = "embedding-macroregions-v2"
ATLAS_LAYOUT_VERSION = "atlas-world-v1"
ATLAS_RANDOM_SEED = 42
REGION_SHAPE_PADDING = 42.0
MIN_WORLD_REGION_PADDING = 0.012
MAX_WORLD_REGION_PADDING = 0.12
WORLD_REGION_PADDING_RATIO = 0.22
BRIDGE_MARGIN_THRESHOLD = 0.12
BRIDGE_SECONDARY_DISTANCE_THRESHOLD = 1.0
REGION_IDENTITY_OVERLAP_THRESHOLD = 0.6
REGION_IDENTITY_CENTROID_THRESHOLD = 0.2
SEMANTIC_EDGE_EXTRA_BUDGET_DIVISOR = 3
MACROREGION_THRESHOLD_CANDIDATES = (
    0.92,
    0.88,
    0.84,
    0.8,
    0.76,
    0.72,
    0.68,
    0.64,
    0.6,
    0.56,
    0.52,
    0.48,
    0.44,
    0.4,
    0.36,
    0.32,
    0.28,
    0.24,
    0.2,
)
_GENERIC_REGION_LABELS = {
    "calendar",
    "chrome",
    "instagram",
    "settings",
    "terminal",
    "tiktok",
    "twitter",
    "x",
    "youtube",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class _AtlasPoint:
    source_item_id: int
    cluster_key: str
    x: float
    y: float
    vector: list[float]
    semantic_summary: str | None
    app_hint: str | None
    connector_instance_id: str
    screen_category: str
    has_knowledge: bool
    observed_at: datetime | None
    object_refs: list[str]
    knowledge_count: int
    searchable_labels: list[str]
    cluster_hints: list[str]


@dataclass(slots=True)
class _SemanticRegionSource:
    cluster_key: str
    title: str
    x: float
    y: float
    top_labels: list[str]
    top_apps: list[str]
    time_start: datetime | None
    time_end: datetime | None
    items: list[_AtlasPoint]
    centroid_vector: list[float] | None = None


@dataclass(slots=True)
class _ProjectionBasis:
    origin: list[float]
    axis_x: list[float]
    axis_y: list[float]


@dataclass(slots=True)
class _MacroRegionGroup:
    region_sources: list[_SemanticRegionSource]
    vector_sum: list[float]
    weight_total: float
    centroid_vector: list[float]


@dataclass(slots=True)
class _LatestSemanticMapRun:
    map_run_id: int
    source_snapshot_id: str
    corpus_hash: str
    embedding_type: str
    embedding_model: str
    embedding_version: str
    regions: list[_SemanticRegionSource]
    points_by_id: dict[int, _AtlasPoint]

    @property
    def source_item_ids(self) -> list[int]:
        return sorted(self.points_by_id)


@dataclass(slots=True)
class _AtlasRegionDraft:
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
    representatives: list[dict[str, object]]
    bridge_neighbors: list[dict[str, object]]
    cohesion_score: float
    centroid_vector: list[float]
    items: list[_AtlasPoint]
    representative_rank_by_source_item_id: dict[int, int]
    subregion_key_by_source_item_id: dict[int, str]
    subregions: list[_AtlasRegionDraft]


@dataclass(slots=True)
class _AtlasItemDraft:
    source_item_id: int
    region_key: str
    subregion_key: str | None
    x: float
    y: float
    semantic_summary: str | None
    app_hint: str | None
    connector_instance_id: str
    screen_category: str
    has_knowledge: bool
    observed_at: datetime | None
    object_refs: list[str]
    is_representative: bool
    representative_rank: int | None
    is_bridge: bool
    bridge_type: str | None
    secondary_region_key: str | None
    bridge_score: float
    screenshot_detail_url: str


@dataclass(slots=True)
class _AtlasEdgeDraft:
    source_region_key: str
    target_region_key: str
    weight: float
    edge_type: str


def derive_subregion_count(item_count: int) -> int:
    if item_count < 8:
        return 0
    if item_count < 20:
        return 3
    if item_count < 40:
        return 4
    if item_count < 80:
        return 6
    return 8


def select_representatives(
    items: list[AtlasCandidateItem],
    *,
    limit: int,
) -> list[AtlasCandidateItem]:
    if limit <= 0 or not items:
        return []

    medoid_distances = _compute_medoid_distances(items)

    deduplicated_items = list(_select_best_duplicate_candidates(items, medoid_distances).values())
    deduplicated_medoid_distances = _compute_medoid_distances(deduplicated_items)

    ordered = sorted(
        deduplicated_items,
        key=lambda item: (
            deduplicated_medoid_distances[item.source_item_id],
            -item.metadata_score,
            item.source_item_id,
        ),
    )

    selected: list[AtlasCandidateItem] = []
    for candidate in ordered:
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def classify_bridge(
    *,
    primary_region_key: str,
    secondary_region_key: str,
    primary_distance: float,
    secondary_distance: float,
    same_parent: bool,
) -> BridgeClassification | None:
    margin = secondary_distance - primary_distance
    if margin < 0.0 or margin > BRIDGE_MARGIN_THRESHOLD:
        return None

    if secondary_distance > BRIDGE_SECONDARY_DISTANCE_THRESHOLD:
        return None

    return BridgeClassification(
        primary_region_key=primary_region_key,
        secondary_region_key=secondary_region_key,
        bridge_type="internal_bridge" if same_parent else "external_bridge",
        bridge_score=max(0.0, 1.0 - (margin / BRIDGE_MARGIN_THRESHOLD)),
    )


def match_region_identity(
    *,
    prior_regions: list[PriorRegionIdentity],
    source_item_ids: set[int],
    centroid: list[float],
    label_tokens: set[str],
) -> str | None:
    if not prior_regions or not source_item_ids:
        return None

    ranked_matches: list[tuple[tuple[float, float, int, str], str]] = []
    for prior_region in prior_regions:
        shared_count = len(prior_region.source_item_ids & source_item_ids)
        if shared_count == 0:
            continue

        overlap = shared_count / max(len(prior_region.source_item_ids), len(source_item_ids))
        if overlap < REGION_IDENTITY_OVERLAP_THRESHOLD:
            continue

        centroid_distance = _vector_distance(prior_region.centroid, centroid)
        if centroid_distance > REGION_IDENTITY_CENTROID_THRESHOLD:
            continue

        label_overlap = len(prior_region.label_tokens & label_tokens)
        ranked_matches.append(
            (
                (
                    -overlap,
                    centroid_distance,
                    -label_overlap,
                    prior_region.region_key,
                ),
                prior_region.region_key,
            )
        )

    if not ranked_matches:
        return None

    return min(ranked_matches)[1]


def rebuild_screenshot_atlas(session: Session, *, force: bool = False) -> dict[str, object]:
    active_runs = _count_running_screenshot_pipeline_runs(session)
    if active_runs > 0 and not force:
        raise RuntimeError(f"active screenshot pipeline runs: {active_runs}")

    latest_map_run = _load_latest_semantic_map_run(session)
    if latest_map_run is None:
        raise RuntimeError("semantic map run is required before atlas rebuild")

    prior_region_identities = _load_prior_region_identities(
        session,
        points_by_id=latest_map_run.points_by_id,
    )
    top_regions = _build_top_regions(
        latest_map_run=latest_map_run,
        prior_region_identities=prior_region_identities,
    )
    item_drafts, bridge_pairs = _build_item_drafts(top_regions)
    edge_drafts, neighbors_by_region_key = _build_edge_drafts(top_regions, bridge_pairs)
    for region in top_regions:
        region.bridge_neighbors = neighbors_by_region_key.get(region.region_key, [])

    timestamp = _utcnow()
    atlas_run = AtlasRun(
        atlas_key=ATLAS_KEY,
        source_family="screenshot",
        status="completed",
        source_count=len(latest_map_run.source_item_ids),
        source_snapshot_id=latest_map_run.source_snapshot_id,
        corpus_hash=latest_map_run.corpus_hash,
        embedding_type=latest_map_run.embedding_type,
        embedding_model=latest_map_run.embedding_model,
        embedding_version=latest_map_run.embedding_version,
        clustering_method=ATLAS_CLUSTERING_METHOD,
        clustering_params_json=json.dumps(
            {
                "bridge_margin": BRIDGE_MARGIN_THRESHOLD,
                "macroregion_thresholds": list(MACROREGION_THRESHOLD_CANDIDATES),
                "subregion_source": "semantic_clusters",
                "topology": "embedding-macroregions",
            },
            sort_keys=True,
        ),
        random_seed=ATLAS_RANDOM_SEED,
        layout_version=ATLAS_LAYOUT_VERSION,
        completed_at=timestamp,
        published_at=timestamp,
    )
    session.add(atlas_run)
    session.flush()

    _persist_regions(session, atlas_run_id=atlas_run.id, top_regions=top_regions)
    _persist_items(session, atlas_run_id=atlas_run.id, item_drafts=item_drafts)
    _persist_edges(session, atlas_run_id=atlas_run.id, edge_drafts=edge_drafts)

    region_count = len(top_regions) + sum(len(region.subregions) for region in top_regions)
    return {
        "atlas_run_id": atlas_run.id,
        "region_count": region_count,
        "item_count": len(item_drafts),
        "top_region_keys": sorted(region.region_key for region in top_regions),
    }


def _load_latest_semantic_map_run(session: Session) -> _LatestSemanticMapRun | None:
    map_run = session.scalar(
        select(SemanticMapRun)
        .where(SemanticMapRun.map_key == "screenshots_semantic_v1")
        .order_by(SemanticMapRun.id.desc())
    )
    if map_run is None:
        return None

    clusters = session.scalars(
        select(SemanticCluster)
        .where(SemanticCluster.map_run_id == map_run.id)
        .order_by(SemanticCluster.id.asc())
    ).all()
    embedding_type, embedding_model, embedding_version = _load_semantic_map_snapshot_metadata(map_run)

    map_points = session.scalars(
        select(SemanticMapPoint)
        .where(SemanticMapPoint.map_run_id == map_run.id)
        .order_by(SemanticMapPoint.id.asc())
    ).all()
    source_item_ids = [point.source_item_id for point in map_points]
    embedding_rows = session.scalars(
        select(Embedding)
        .where(
            Embedding.embedding_type == ATLAS_EMBEDDING_TYPE,
            Embedding.source_item_id.in_(source_item_ids),
        )
        .order_by(Embedding.id.asc())
    ).all()
    embedding_by_source_item_id = {
        int(embedding_row.source_item_id): embedding_row
        for embedding_row in embedding_rows
        if embedding_row.source_item_id is not None
    }
    interpretations_by_source_item_id = {
        row.source_item_id: row
        for row in session.scalars(
            select(AssetInterpretation)
            .where(AssetInterpretation.source_item_id.in_(source_item_ids))
            .order_by(AssetInterpretation.source_item_id.asc())
        ).all()
    }
    source_items_by_id = {
        row.id: row
        for row in session.scalars(
            select(SourceItem)
            .where(SourceItem.id.in_(source_item_ids))
            .order_by(SourceItem.id.asc())
        ).all()
    }
    object_refs_by_source_item_id = _load_object_refs_by_source_item_id(
        session,
        source_item_ids=source_item_ids,
    )
    knowledge_counts_by_source_item_id = _load_knowledge_counts_by_source_item_id(
        session,
        source_item_ids=source_item_ids,
    )

    points_by_id: dict[int, _AtlasPoint] = {}
    grouped_source_item_ids: dict[str, list[int]] = defaultdict(list)
    for point in map_points:
        interpretation = interpretations_by_source_item_id.get(point.source_item_id)
        source_item = source_items_by_id.get(point.source_item_id)
        embedding_row = embedding_by_source_item_id.get(point.source_item_id)
        if (
            interpretation is None
            or source_item is None
            or embedding_row is None
            or point.cluster_key is None
        ):
            continue

        atlas_point = _AtlasPoint(
            source_item_id=point.source_item_id,
            cluster_key=point.cluster_key,
            x=0.0,
            y=0.0,
            vector=embed_text(embedding_row.content_text),
            semantic_summary=interpretation.semantic_summary,
            app_hint=interpretation.app_hint,
            connector_instance_id=source_item.connector_instance_id,
            screen_category=interpretation.screen_category,
            has_knowledge=knowledge_counts_by_source_item_id.get(point.source_item_id, 0) > 0,
            observed_at=source_item.source_observed_at or source_item.source_created_at,
            object_refs=object_refs_by_source_item_id.get(point.source_item_id, []),
            knowledge_count=knowledge_counts_by_source_item_id.get(point.source_item_id, 0),
            searchable_labels=json.loads(interpretation.searchable_labels_json or "[]"),
            cluster_hints=json.loads(interpretation.cluster_hints_json or "[]"),
        )
        points_by_id[point.source_item_id] = atlas_point
        grouped_source_item_ids[atlas_point.cluster_key].append(atlas_point.source_item_id)

    basis = _build_projection_basis([point.vector for point in points_by_id.values()])
    for atlas_point in points_by_id.values():
        atlas_point.x, atlas_point.y = _project_vector_to_world(atlas_point.vector, basis)

    regions: list[_SemanticRegionSource] = []
    for cluster in clusters:
        cluster_points = [
            points_by_id[source_item_id]
            for source_item_id in grouped_source_item_ids.get(cluster.cluster_key, [])
            if source_item_id in points_by_id
        ]
        if not cluster_points:
            continue
        summary = _summarize_points(cluster_points, fallback_title=cluster.title or cluster.cluster_key)
        regions.append(
            _SemanticRegionSource(
                cluster_key=cluster.cluster_key,
                title=str(summary["title"] or cluster.title or cluster.cluster_key),
                x=round(sum(point.x for point in cluster_points) / len(cluster_points), 6),
                y=round(sum(point.y for point in cluster_points) / len(cluster_points), 6),
                top_labels=list(summary["top_labels"]),
                top_apps=list(summary["top_apps"]),
                time_start=summary["time_start"],
                time_end=summary["time_end"],
                items=cluster_points,
                centroid_vector=_normalized_mean_vector([point.vector for point in cluster_points]),
            )
        )

    source_snapshot_id, corpus_hash = _atlas_input_snapshot_identity(
        map_run_id=map_run.id,
        embedding_type=embedding_type,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        regions=regions,
        points_by_id=points_by_id,
    )

    return _LatestSemanticMapRun(
        map_run_id=map_run.id,
        source_snapshot_id=source_snapshot_id,
        corpus_hash=corpus_hash,
        embedding_type=embedding_type,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        regions=regions,
        points_by_id=points_by_id,
    )


def _load_prior_region_identities(
    session: Session,
    *,
    points_by_id: dict[int, _AtlasPoint],
) -> list[PriorRegionIdentity]:
    prior_run = session.scalar(
        select(AtlasRun)
        .where(AtlasRun.atlas_key == ATLAS_KEY, AtlasRun.status == "completed")
        .order_by(AtlasRun.id.desc())
    )
    if prior_run is None:
        return []

    prior_regions = session.scalars(
        select(AtlasRegion)
        .where(AtlasRegion.atlas_run_id == prior_run.id, AtlasRegion.level == 0)
        .order_by(AtlasRegion.region_key.asc())
    ).all()
    prior_items = session.scalars(
        select(AtlasItem).where(AtlasItem.atlas_run_id == prior_run.id).order_by(AtlasItem.id.asc())
    ).all()
    source_ids_by_region_key: dict[str, set[int]] = defaultdict(set)
    for item in prior_items:
        source_ids_by_region_key[item.region_key].add(item.source_item_id)

    identities: list[PriorRegionIdentity] = []
    for region in prior_regions:
        source_item_ids = source_ids_by_region_key.get(region.region_key, set())
        centroid = _normalized_mean_vector(
            [points_by_id[source_item_id].vector for source_item_id in sorted(source_item_ids) if source_item_id in points_by_id]
        )
        if not centroid:
            continue
        identities.append(
            PriorRegionIdentity(
                region_key=region.region_key,
                source_item_ids=source_item_ids,
                centroid=centroid,
                label_tokens=_tokenize_strings(
                    [region.title, *json.loads(region.top_labels_json or "[]")]
                ),
            )
        )
    return identities


def _build_top_regions(
    *,
    latest_map_run: _LatestSemanticMapRun,
    prior_region_identities: list[PriorRegionIdentity],
) -> list[_AtlasRegionDraft]:
    macroregion_groups = _cluster_atomic_regions_into_macroregions(latest_map_run.regions)
    atlas_center = _compute_atlas_center(latest_map_run.regions)
    top_regions: list[_AtlasRegionDraft] = []
    for macro_index, group in enumerate(macroregion_groups, start=1):
        group_items = [
            item
            for region_source in group.region_sources
            for item in region_source.items
        ]
        current_source_item_ids = {item.source_item_id for item in group_items}
        centroid_vector = group.centroid_vector
        top_summary = _summarize_points(
            group_items,
            fallback_title=group.region_sources[0].title,
        )
        region_key = match_region_identity(
            prior_regions=prior_region_identities,
            source_item_ids=current_source_item_ids,
            centroid=centroid_vector,
            label_tokens=_tokenize_strings([top_summary["title"], *top_summary["top_labels"]]),
        )
        if region_key is None:
            region_key = f"region-macro-{macro_index:03d}"

        representative_rank_by_source_item_id = _representative_rank_by_source_item_id(group_items)
        subregions, subregion_key_by_source_item_id = _build_subregions(
            parent_region_key=region_key,
            region_sources=group.region_sources,
            atlas_center=atlas_center,
        )
        region_x = round(sum(item.x for item in group_items) / len(group_items), 6)
        region_y = round(sum(item.y for item in group_items) / len(group_items), 6)
        region_shape = _build_region_shape(group_items)
        label_x, label_y = _compute_label_anchor(
            region_x=region_x,
            region_y=region_y,
            region_shape=region_shape,
            atlas_center=atlas_center,
        )

        top_regions.append(
            _AtlasRegionDraft(
                region_key=region_key,
                parent_region_key=None,
                level=0,
                title=top_summary["title"],
                x=region_x,
                y=region_y,
                label_x=label_x,
                label_y=label_y,
                region_shape=region_shape,
                item_count=len(group_items),
                top_labels=top_summary["top_labels"],
                top_apps=top_summary["top_apps"],
                top_people=top_summary["top_people"],
                top_entities=top_summary["top_entities"],
                time_start=top_summary["time_start"],
                time_end=top_summary["time_end"],
                representatives=_representatives_payload(representative_rank_by_source_item_id),
                bridge_neighbors=[],
                cohesion_score=_cohesion_score(group_items, centroid_vector),
                centroid_vector=centroid_vector,
                items=group_items,
                representative_rank_by_source_item_id=representative_rank_by_source_item_id,
                subregion_key_by_source_item_id=subregion_key_by_source_item_id,
                subregions=subregions,
            )
        )
    return top_regions


def _build_subregions(
    *,
    parent_region_key: str,
    region_sources: list[_SemanticRegionSource],
    atlas_center: tuple[float, float],
) -> tuple[list[_AtlasRegionDraft], dict[int, str]]:
    if not region_sources:
        return [], {}

    subregions: list[_AtlasRegionDraft] = []
    subregion_key_by_source_item_id: dict[int, str] = {}
    for region_source in sorted(
        region_sources,
        key=lambda source: (-len(source.items), source.cluster_key),
    ):
        centroid_vector = _region_source_centroid(region_source)
        subregion_summary = _summarize_points(
            region_source.items,
            fallback_title=region_source.title,
        )
        subregion_x = round(sum(item.x for item in region_source.items) / len(region_source.items), 6)
        subregion_y = round(sum(item.y for item in region_source.items) / len(region_source.items), 6)
        subregion_key = f"{parent_region_key}/subregion-{region_source.cluster_key}"
        region_shape = _build_region_shape(region_source.items, padding=24.0)
        label_x, label_y = _compute_label_anchor(
            region_x=subregion_x,
            region_y=subregion_y,
            region_shape=region_shape,
            atlas_center=atlas_center,
        )
        representative_rank_by_source_item_id = _representative_rank_by_source_item_id(
            region_source.items,
            limit=3,
        )
        for item in region_source.items:
            subregion_key_by_source_item_id[item.source_item_id] = subregion_key

        subregions.append(
            _AtlasRegionDraft(
                region_key=subregion_key,
                parent_region_key=parent_region_key,
                level=1,
                title=subregion_summary["title"],
                x=subregion_x,
                y=subregion_y,
                label_x=label_x,
                label_y=label_y,
                region_shape=region_shape,
                item_count=len(region_source.items),
                top_labels=subregion_summary["top_labels"],
                top_apps=subregion_summary["top_apps"],
                top_people=subregion_summary["top_people"],
                top_entities=subregion_summary["top_entities"],
                time_start=subregion_summary["time_start"],
                time_end=subregion_summary["time_end"],
                representatives=_representatives_payload(representative_rank_by_source_item_id),
                bridge_neighbors=[],
                cohesion_score=_cohesion_score(region_source.items, centroid_vector),
                centroid_vector=centroid_vector,
                items=region_source.items,
                representative_rank_by_source_item_id=representative_rank_by_source_item_id,
                subregion_key_by_source_item_id={},
                subregions=[],
            )
        )

    _assign_subregion_bridge_neighbors(subregions)
    return subregions, subregion_key_by_source_item_id


def _cluster_atomic_regions_into_macroregions(
    region_sources: list[_SemanticRegionSource],
) -> list[_MacroRegionGroup]:
    if not region_sources:
        return []

    ordered_sources = sorted(
        region_sources,
        key=lambda source: (-len(source.items), source.cluster_key),
    )
    target_cap = min(24, max(2, round(math.sqrt(len(ordered_sources)))))
    target_floor = max(2, target_cap // 2)
    candidate_results: list[tuple[int, float, list[_MacroRegionGroup]]] = []
    for threshold in MACROREGION_THRESHOLD_CANDIDATES:
        groups = _greedy_cluster_atomic_regions(ordered_sources, similarity_threshold=threshold)
        candidate_results.append((len(groups), threshold, groups))
        if target_floor <= len(groups) <= target_cap:
            return groups

    overflow_candidates = [
        (count - target_cap, -threshold, groups)
        for count, threshold, groups in candidate_results
        if count > target_cap
    ]
    if overflow_candidates:
        return min(overflow_candidates)[2]

    underflow_candidates = [
        (target_floor - count, -threshold, groups)
        for count, threshold, groups in candidate_results
    ]
    return min(underflow_candidates)[2]


def _greedy_cluster_atomic_regions(
    region_sources: list[_SemanticRegionSource],
    *,
    similarity_threshold: float,
) -> list[_MacroRegionGroup]:
    groups: list[_MacroRegionGroup] = []
    for region_source in region_sources:
        centroid_vector = _region_source_centroid(region_source)
        weight = float(len(region_source.items))
        best_group: _MacroRegionGroup | None = None
        best_score = -1.0
        for group in groups:
            score = _cosine_similarity(centroid_vector, group.centroid_vector)
            if score > best_score:
                best_score = score
                best_group = group

        if best_group is None or best_score < similarity_threshold:
            groups.append(
                _MacroRegionGroup(
                    region_sources=[region_source],
                    vector_sum=[value * weight for value in centroid_vector],
                    weight_total=weight,
                    centroid_vector=centroid_vector,
                )
            )
            continue

        best_group.region_sources.append(region_source)
        best_group.weight_total += weight
        for index, value in enumerate(centroid_vector):
            best_group.vector_sum[index] += value * weight
        best_group.centroid_vector = _normalize_vector(best_group.vector_sum)

    return sorted(
        groups,
        key=lambda group: (
            -sum(len(region_source.items) for region_source in group.region_sources),
            group.region_sources[0].cluster_key,
        ),
    )


def _region_source_centroid(region_source: _SemanticRegionSource) -> list[float]:
    if region_source.centroid_vector:
        return region_source.centroid_vector
    return _normalized_mean_vector([item.vector for item in region_source.items])


def _compute_atlas_center(region_sources: list[_SemanticRegionSource]) -> tuple[float, float]:
    if not region_sources:
        return (0.0, 0.0)
    return (
        sum(region_source.x for region_source in region_sources) / len(region_sources),
        sum(region_source.y for region_source in region_sources) / len(region_sources),
    )


def _build_item_drafts(
    top_regions: list[_AtlasRegionDraft],
) -> tuple[list[_AtlasItemDraft], Counter[tuple[str, str]]]:
    region_centroids = {region.region_key: region.centroid_vector for region in top_regions}
    bridge_pairs: Counter[tuple[str, str]] = Counter()
    item_drafts: list[_AtlasItemDraft] = []

    for region in top_regions:
        for item in region.items:
            classification = _classify_point_bridge(
                point=item,
                primary_region_key=region.region_key,
                region_centroids=region_centroids,
            )
            if classification is not None:
                bridge_pairs[_ordered_pair(region.region_key, classification.secondary_region_key)] += 1

            representative_rank = region.representative_rank_by_source_item_id.get(item.source_item_id)
            item_drafts.append(
                _AtlasItemDraft(
                    source_item_id=item.source_item_id,
                    region_key=region.region_key,
                    subregion_key=region.subregion_key_by_source_item_id.get(item.source_item_id),
                    x=item.x,
                    y=item.y,
                    semantic_summary=item.semantic_summary,
                    app_hint=item.app_hint,
                    connector_instance_id=item.connector_instance_id,
                    screen_category=item.screen_category,
                    has_knowledge=item.has_knowledge,
                    observed_at=item.observed_at,
                    object_refs=item.object_refs,
                    is_representative=representative_rank is not None,
                    representative_rank=representative_rank,
                    is_bridge=classification is not None,
                    bridge_type=None if classification is None else classification.bridge_type,
                    secondary_region_key=None if classification is None else classification.secondary_region_key,
                    bridge_score=0.0 if classification is None else round(classification.bridge_score, 6),
                    screenshot_detail_url=f"/screenshots/{item.source_item_id}",
                )
            )

    return item_drafts, bridge_pairs


def _build_edge_drafts(
    top_regions: list[_AtlasRegionDraft],
    bridge_pairs: Counter[tuple[str, str]],
) -> tuple[list[_AtlasEdgeDraft], dict[str, list[dict[str, object]]]]:
    edge_drafts: list[_AtlasEdgeDraft] = []
    neighbors_by_region_key: dict[str, list[dict[str, object]]] = defaultdict(list)

    for semantic_edge in _build_sparse_semantic_edge_drafts(top_regions):
        edge_drafts.append(semantic_edge)
        neighbors_by_region_key[semantic_edge.source_region_key].append(
            {
                "edge_type": semantic_edge.edge_type,
                "region_key": semantic_edge.target_region_key,
                "weight": semantic_edge.weight,
            }
        )
        neighbors_by_region_key[semantic_edge.target_region_key].append(
            {
                "edge_type": semantic_edge.edge_type,
                "region_key": semantic_edge.source_region_key,
                "weight": semantic_edge.weight,
            }
        )

    for left_region, right_region in combinations(sorted(top_regions, key=lambda region: region.region_key), 2):
        bridge_count = bridge_pairs.get(_ordered_pair(left_region.region_key, right_region.region_key), 0)
        if bridge_count > 0:
            bridge_weight = float(bridge_count)
            edge_drafts.append(
                _AtlasEdgeDraft(
                    source_region_key=left_region.region_key,
                    target_region_key=right_region.region_key,
                    weight=bridge_weight,
                    edge_type="semantic_bridge",
                )
            )
            neighbors_by_region_key[left_region.region_key].append(
                {
                    "edge_type": "semantic_bridge",
                    "region_key": right_region.region_key,
                    "weight": bridge_weight,
                }
            )
            neighbors_by_region_key[right_region.region_key].append(
                {
                    "edge_type": "semantic_bridge",
                    "region_key": left_region.region_key,
                    "weight": bridge_weight,
                }
            )

    for region_key, neighbors in neighbors_by_region_key.items():
        neighbors_by_region_key[region_key] = sorted(
            neighbors,
            key=lambda neighbor: (
                neighbor["edge_type"],
                -float(neighbor["weight"]),
                str(neighbor["region_key"]),
            ),
        )

    return edge_drafts, neighbors_by_region_key


def _assign_subregion_bridge_neighbors(subregions: list[_AtlasRegionDraft]) -> None:
    neighbor_payloads = _build_neighbor_payloads(
        subregions,
        edge_type="internal_bridge",
        extra_budget_divisor=2,
    )
    for subregion in subregions:
        subregion.bridge_neighbors = neighbor_payloads.get(subregion.region_key, [])


def _build_sparse_semantic_edge_drafts(
    top_regions: list[_AtlasRegionDraft],
) -> list[_AtlasEdgeDraft]:
    return [
        _AtlasEdgeDraft(
            source_region_key=source_region_key,
            target_region_key=target_region_key,
            weight=weight,
            edge_type=edge_type,
        )
        for source_region_key, target_region_key, weight, edge_type in _build_sparse_links(
            top_regions,
            edge_type="semantic_similarity",
            extra_budget_divisor=SEMANTIC_EDGE_EXTRA_BUDGET_DIVISOR,
        )
    ]


def _build_neighbor_payloads(
    regions: list[_AtlasRegionDraft],
    *,
    edge_type: str,
    extra_budget_divisor: int,
) -> dict[str, list[dict[str, object]]]:
    neighbors_by_region_key: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source_region_key, target_region_key, weight, resolved_edge_type in _build_sparse_links(
        regions,
        edge_type=edge_type,
        extra_budget_divisor=extra_budget_divisor,
    ):
        neighbors_by_region_key[source_region_key].append(
            {
                "edge_type": resolved_edge_type,
                "region_key": target_region_key,
                "weight": weight,
            }
        )
        neighbors_by_region_key[target_region_key].append(
            {
                "edge_type": resolved_edge_type,
                "region_key": source_region_key,
                "weight": weight,
            }
        )

    for region_key, neighbors in neighbors_by_region_key.items():
        neighbors_by_region_key[region_key] = sorted(
            neighbors,
            key=lambda neighbor: (-float(neighbor["weight"]), str(neighbor["region_key"])),
        )
    return neighbors_by_region_key


def _build_sparse_links(
    regions: list[_AtlasRegionDraft],
    *,
    edge_type: str,
    extra_budget_divisor: int,
) -> list[tuple[str, str, float, str]]:
    ordered_regions = sorted(regions, key=lambda region: region.region_key)
    if len(ordered_regions) < 2:
        return []

    candidates: list[tuple[float, str, str]] = []
    for left_region, right_region in combinations(ordered_regions, 2):
        candidates.append(
            (
                round(_signal_similarity(left_region.centroid_vector, right_region.centroid_vector), 6),
                left_region.region_key,
                right_region.region_key,
            )
        )
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1], candidate[2]))

    selected_pairs: set[tuple[str, str]] = set()
    degree_by_region_key: Counter[str] = Counter()
    parent_by_region_key = {region.region_key: region.region_key for region in ordered_regions}

    def _find(region_key: str) -> str:
        parent = parent_by_region_key[region_key]
        if parent == region_key:
            return parent
        parent_by_region_key[region_key] = _find(parent)
        return parent_by_region_key[region_key]

    def _union(left_key: str, right_key: str) -> bool:
        left_root = _find(left_key)
        right_root = _find(right_key)
        if left_root == right_root:
            return False
        parent_by_region_key[right_root] = left_root
        return True

    selected_edges: list[tuple[str, str, float, str]] = []
    for weight, left_key, right_key in candidates:
        if not _union(left_key, right_key):
            continue
        selected_pairs.add((left_key, right_key))
        degree_by_region_key[left_key] += 1
        degree_by_region_key[right_key] += 1
        selected_edges.append((left_key, right_key, weight, edge_type))

    extra_budget = max(1, math.ceil(len(ordered_regions) / extra_budget_divisor))
    for weight, left_key, right_key in candidates:
        if extra_budget <= 0 or (left_key, right_key) in selected_pairs:
            continue
        if degree_by_region_key[left_key] >= 2 and degree_by_region_key[right_key] >= 2:
            continue

        selected_pairs.add((left_key, right_key))
        degree_by_region_key[left_key] += 1
        degree_by_region_key[right_key] += 1
        selected_edges.append((left_key, right_key, weight, edge_type))
        extra_budget -= 1

    return sorted(
        selected_edges,
        key=lambda edge: (edge[0], edge[1]),
    )


def _persist_regions(
    session: Session,
    *,
    atlas_run_id: int,
    top_regions: list[_AtlasRegionDraft],
) -> None:
    for region in top_regions:
        _persist_region(session, atlas_run_id=atlas_run_id, region=region)
        for subregion in region.subregions:
            _persist_region(session, atlas_run_id=atlas_run_id, region=subregion)
    session.flush()


def _persist_region(
    session: Session,
    *,
    atlas_run_id: int,
    region: _AtlasRegionDraft,
) -> None:
    session.add(
        AtlasRegion(
            atlas_run_id=atlas_run_id,
            region_key=region.region_key,
            parent_region_key=region.parent_region_key,
            level=region.level,
            title=region.title,
            x=region.x,
            y=region.y,
            label_x=region.label_x,
            label_y=region.label_y,
            region_shape_json=json.dumps(region.region_shape, sort_keys=True),
            item_count=region.item_count,
            top_labels_json=json.dumps(region.top_labels, sort_keys=True),
            top_apps_json=json.dumps(region.top_apps, sort_keys=True),
            top_people_json=json.dumps(region.top_people, sort_keys=True),
            top_entities_json=json.dumps(region.top_entities, sort_keys=True),
            time_start=region.time_start,
            time_end=region.time_end,
            representatives_json=json.dumps(region.representatives, sort_keys=True),
            bridge_neighbors_json=json.dumps(region.bridge_neighbors, sort_keys=True),
            cohesion_score=region.cohesion_score,
        )
    )


def _persist_items(
    session: Session,
    *,
    atlas_run_id: int,
    item_drafts: list[_AtlasItemDraft],
) -> None:
    for item in item_drafts:
        session.add(
            AtlasItem(
                atlas_run_id=atlas_run_id,
                source_item_id=item.source_item_id,
                region_key=item.region_key,
                subregion_key=item.subregion_key,
                x=item.x,
                y=item.y,
                semantic_summary=item.semantic_summary,
                app_hint=item.app_hint,
                connector_instance_id=item.connector_instance_id,
                screen_category=item.screen_category,
                has_knowledge=item.has_knowledge,
                observed_at=item.observed_at,
                object_refs_json=json.dumps(item.object_refs, sort_keys=True),
                is_representative=item.is_representative,
                representative_rank=item.representative_rank,
                is_bridge=item.is_bridge,
                bridge_type=item.bridge_type,
                secondary_region_key=item.secondary_region_key,
                bridge_score=item.bridge_score,
                screenshot_detail_url=item.screenshot_detail_url,
            )
        )
    session.flush()


def _persist_edges(
    session: Session,
    *,
    atlas_run_id: int,
    edge_drafts: list[_AtlasEdgeDraft],
) -> None:
    for edge in edge_drafts:
        session.add(
            AtlasEdge(
                atlas_run_id=atlas_run_id,
                source_region_key=edge.source_region_key,
                target_region_key=edge.target_region_key,
                weight=edge.weight,
                edge_type=edge.edge_type,
            )
        )
    session.flush()


def _count_running_screenshot_pipeline_runs(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(PipelineRun)
            .join(SourceItem, SourceItem.id == PipelineRun.source_item_id)
            .where(PipelineRun.status == "running", SourceItem.source_family == "screenshot")
        )
        or 0
    )


def _representative_rank_by_source_item_id(
    items: list[_AtlasPoint],
    *,
    limit: int = 6,
) -> dict[int, int]:
    candidates = [
        AtlasCandidateItem(
            source_item_id=item.source_item_id,
            vector=item.vector,
            semantic_summary=item.semantic_summary,
            app_hint=item.app_hint,
            object_refs=item.object_refs,
            knowledge_count=item.knowledge_count,
        )
        for item in items
    ]
    ranked = select_representatives(candidates, limit=min(limit, len(candidates)))
    return {
        candidate.source_item_id: rank
        for rank, candidate in enumerate(ranked, start=1)
    }


def _classify_point_bridge(
    *,
    point: _AtlasPoint,
    primary_region_key: str,
    region_centroids: dict[str, list[float]],
) -> BridgeClassification | None:
    primary_centroid = region_centroids.get(primary_region_key)
    if primary_centroid is None:
        return None

    secondary_candidates = sorted(
        (
            (_signal_distance(point.vector, centroid), region_key)
            for region_key, centroid in region_centroids.items()
            if region_key != primary_region_key
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    if not secondary_candidates:
        return None

    primary_distance = _signal_distance(point.vector, primary_centroid)
    secondary_distance, secondary_region_key = secondary_candidates[0]
    return classify_bridge(
        primary_region_key=primary_region_key,
        secondary_region_key=secondary_region_key,
        primary_distance=min(primary_distance, secondary_distance),
        secondary_distance=max(primary_distance, secondary_distance),
        same_parent=False,
    )


def _load_semantic_map_snapshot_metadata(map_run: SemanticMapRun) -> tuple[str, str, str]:
    config = json.loads(map_run.config_json or "{}")
    embedding_type = str(config.get("embedding_type") or ATLAS_EMBEDDING_TYPE)
    embedding_model = str(config.get("embedding_model") or "unknown")
    raw_dimension = config.get("embedding_dimension")
    dimension = int(raw_dimension) if raw_dimension is not None else 0
    raw_version = config.get("embedding_version")
    if isinstance(raw_version, str) and raw_version:
        embedding_version = raw_version
    elif dimension > 0:
        embedding_version = _embedding_version_from_dimension(dimension)
    else:
        embedding_version = "unknown"
    return embedding_type, embedding_model, embedding_version


def _build_projection_basis(vectors: list[list[float]]) -> _ProjectionBasis:
    if not vectors:
        return _ProjectionBasis(origin=[0.0, 0.0], axis_x=[1.0, 0.0], axis_y=[0.0, 1.0])

    origin = _mean_vector(vectors)
    centered_vectors = [
        [value - origin[index] for index, value in enumerate(vector)]
        for vector in vectors
    ]
    dimension = len(vectors[0])
    axis_x = _principal_component(centered_vectors, dimension=dimension)
    residual_vectors = [
        _subtract_projection(vector, axis_x)
        for vector in centered_vectors
    ]
    axis_y = _principal_component(residual_vectors, dimension=dimension)
    if _vector_magnitude(axis_y) == 0.0:
        fallback = [0.0] * dimension
        fallback[1 if dimension > 1 else 0] = 1.0
        axis_y = fallback
    return _ProjectionBasis(origin=origin, axis_x=axis_x, axis_y=axis_y)


def _project_vector_to_world(vector: list[float], basis: _ProjectionBasis) -> tuple[float, float]:
    centered = [value - basis.origin[index] for index, value in enumerate(vector)]
    return (
        round(sum(value * basis.axis_x[index] for index, value in enumerate(centered)), 6),
        round(sum(value * basis.axis_y[index] for index, value in enumerate(centered)), 6),
    )


def _build_region_shape(
    points: list[_AtlasPoint],
    *,
    padding: float = REGION_SHAPE_PADDING,
) -> dict[str, object]:
    if not points:
        return {"rings": [], "shape_type": "polygon"}

    unique_points = sorted({(round(point.x, 6), round(point.y, 6)) for point in points})
    resolved_padding = _resolve_region_shape_padding(unique_points, padding=padding)
    if len(unique_points) < 3:
        xs = [point[0] for point in unique_points]
        ys = [point[1] for point in unique_points]
        min_x = min(xs) - resolved_padding
        max_x = max(xs) + resolved_padding
        min_y = min(ys) - resolved_padding
        max_y = max(ys) + resolved_padding
        ring = [
            {"x": round(min_x, 3), "y": round(min_y, 3)},
            {"x": round(max_x, 3), "y": round(min_y, 3)},
            {"x": round(max_x, 3), "y": round(max_y, 3)},
            {"x": round(min_x, 3), "y": round(max_y, 3)},
            {"x": round(min_x, 3), "y": round(min_y, 3)},
        ]
        return {"shape_type": "polygon", "rings": [ring]}

    hull = _convex_hull(unique_points)
    centroid_x = sum(point[0] for point in hull) / len(hull)
    centroid_y = sum(point[1] for point in hull) / len(hull)
    expanded_ring = []
    for x, y in hull:
        delta_x = x - centroid_x
        delta_y = y - centroid_y
        magnitude = math.sqrt(delta_x * delta_x + delta_y * delta_y)
        if magnitude == 0.0:
            expanded_x = x
            expanded_y = y
        else:
            expansion = resolved_padding / magnitude
            expanded_x = x + delta_x * expansion
            expanded_y = y + delta_y * expansion
        expanded_ring.append({"x": round(expanded_x, 3), "y": round(expanded_y, 3)})
    if expanded_ring:
        expanded_ring.append(dict(expanded_ring[0]))
    return {
        "shape_type": "polygon",
        "rings": [expanded_ring],
    }


def _region_bounds(region_shape: dict[str, object]) -> tuple[float, float, float, float]:
    ring_values = region_shape.get("rings")
    if not isinstance(ring_values, list) or not ring_values:
        return (0.0, 0.0, 0.0, 0.0)

    xs: list[float] = []
    ys: list[float] = []
    for ring in ring_values:
        if not isinstance(ring, list):
            continue
        for point in ring:
            x_value: object | None = None
            y_value: object | None = None
            if isinstance(point, dict):
                x_value = point.get("x")
                y_value = point.get("y")
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                x_value = point[0]
                y_value = point[1]
            if isinstance(x_value, int | float) and isinstance(y_value, int | float):
                xs.append(float(x_value))
                ys.append(float(y_value))

    if not xs or not ys:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _compute_label_anchor(
    *,
    region_x: float,
    region_y: float,
    region_shape: dict[str, object],
    atlas_center: tuple[float, float],
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = _region_bounds(region_shape)
    span = max(max_x - min_x, max_y - min_y, 0.02)
    offset = max(0.018, min(0.06, span * 0.35))
    horizontal = -offset if region_x >= atlas_center[0] else offset
    vertical = -offset if region_y >= atlas_center[1] else offset
    return (region_x + horizontal, region_y + vertical)


def _resolve_region_shape_padding(
    unique_points: Sequence[tuple[float, float]],
    *,
    padding: float,
) -> float:
    if padding <= 1.0:
        return max(float(padding), MIN_WORLD_REGION_PADDING)

    if not unique_points:
        return MIN_WORLD_REGION_PADDING

    xs = [point[0] for point in unique_points]
    ys = [point[1] for point in unique_points]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    local_span = max(span_x, span_y)
    if local_span == 0.0 and len(unique_points) > 1:
        local_span = max(
            math.dist(unique_points[index], unique_points[index - 1])
            for index in range(1, len(unique_points))
        )

    if local_span == 0.0:
        return MIN_WORLD_REGION_PADDING

    return min(
        MAX_WORLD_REGION_PADDING,
        max(MIN_WORLD_REGION_PADDING, local_span * WORLD_REGION_PADDING_RATIO),
    )


def _summarize_points(
    points: list[_AtlasPoint],
    *,
    fallback_title: str,
) -> dict[str, object]:
    label_counts: Counter[str] = Counter()
    app_counts: Counter[str] = Counter()
    people_counts: Counter[str] = Counter()
    entity_counts: Counter[str] = Counter()
    observed_values: list[datetime] = []

    for point in points:
        labels = point.cluster_hints or point.searchable_labels
        for label in labels:
            label_counts[label] += 1
        if point.app_hint:
            app_counts[point.app_hint] += 1
        for object_ref in point.object_refs:
            entity_counts[object_ref] += 1
            if object_ref.startswith("person:"):
                people_counts[object_ref] += 1
        if point.observed_at is not None:
            observed_values.append(point.observed_at)

    top_labels = [label for label, _count in label_counts.most_common(4)]
    top_apps = [app for app, _count in app_counts.most_common(3)]
    top_people = [person for person, _count in people_counts.most_common(3)]
    top_entities = [entity for entity, _count in entity_counts.most_common(5)]
    title = _build_region_title(
        top_labels=top_labels,
        top_apps=top_apps,
        fallback_title=fallback_title,
    )

    return {
        "title": title,
        "top_apps": top_apps,
        "top_entities": top_entities,
        "top_labels": top_labels,
        "top_people": top_people,
        "time_end": max(observed_values) if observed_values else None,
        "time_start": min(observed_values) if observed_values else None,
    }


def _normalize_title_token(value: str) -> str | None:
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized or None


def _is_generic_region_label(value: str) -> bool:
    normalized = _normalize_title_token(value)
    return normalized in _GENERIC_REGION_LABELS if normalized else False


def _build_region_title(
    *,
    top_labels: list[str],
    top_apps: list[str],
    fallback_title: str,
) -> str:
    semantic_labels = [label for label in top_labels if not _is_generic_region_label(label)]
    top_app = top_apps[0] if top_apps else None

    if top_app and semantic_labels:
        return f"{top_app} · {semantic_labels[0]}"
    if len(semantic_labels) >= 2:
        return f"{semantic_labels[0]}, {semantic_labels[1]}"
    if semantic_labels:
        return semantic_labels[0]
    if top_app:
        return top_app
    return fallback_title


def _load_object_refs_by_source_item_id(
    session: Session,
    *,
    source_item_ids: list[int],
) -> dict[int, list[str]]:
    if not source_item_ids:
        return {}

    links = session.execute(
        select(
            KnowledgeEvidenceLink.source_item_id,
            KnowledgeClaim.subject_ref,
            KnowledgeClaim.object_ref_or_value,
        )
        .join(KnowledgeClaim, KnowledgeClaim.id == KnowledgeEvidenceLink.claim_id)
        .where(KnowledgeEvidenceLink.source_item_id.in_(source_item_ids))
    ).all()

    refs_by_source_item_id: dict[int, set[str]] = defaultdict(set)
    all_refs: set[str] = set()
    for source_item_id, subject_ref, object_ref_or_value in links:
        refs_by_source_item_id[int(source_item_id)].add(str(subject_ref))
        all_refs.add(str(subject_ref))
        if ":" in str(object_ref_or_value):
            refs_by_source_item_id[int(source_item_id)].add(str(object_ref_or_value))
            all_refs.add(str(object_ref_or_value))

    existing_refs = set(
        session.scalars(
            select(KnowledgeObject.slug).where(KnowledgeObject.slug.in_(sorted(all_refs)))
        ).all()
    )
    return {
        source_item_id: sorted(
            ref for ref in refs if ref in existing_refs or ref.startswith("thread:")
        )
        for source_item_id, refs in refs_by_source_item_id.items()
    }


def _load_knowledge_counts_by_source_item_id(
    session: Session,
    *,
    source_item_ids: list[int],
) -> dict[int, int]:
    if not source_item_ids:
        return {}

    rows = session.execute(
        select(
            KnowledgeEvidenceLink.source_item_id,
            func.count(func.distinct(KnowledgeEvidenceLink.claim_id)),
        )
        .where(KnowledgeEvidenceLink.source_item_id.in_(source_item_ids))
        .group_by(KnowledgeEvidenceLink.source_item_id)
    ).all()
    return {int(source_item_id): int(claim_count) for source_item_id, claim_count in rows}


def _representatives_payload(
    representative_rank_by_source_item_id: dict[int, int],
) -> list[dict[str, object]]:
    return [
        {"rank": rank, "source_item_id": source_item_id}
        for source_item_id, rank in sorted(
            representative_rank_by_source_item_id.items(),
            key=lambda entry: entry[1],
        )
    ]


def _atlas_input_snapshot_identity(
    *,
    map_run_id: int,
    embedding_type: str,
    embedding_model: str,
    embedding_version: str,
    regions: list[_SemanticRegionSource],
    points_by_id: dict[int, _AtlasPoint],
) -> tuple[str, str]:
    payload = {
        "embedding_model": embedding_model,
        "embedding_type": embedding_type,
        "embedding_version": embedding_version,
        "map_run_id": map_run_id,
        "points": [
            {
                "app_hint": point.app_hint,
                "cluster_hints": point.cluster_hints,
                "cluster_key": point.cluster_key,
                "connector_instance_id": point.connector_instance_id,
                "has_knowledge": point.has_knowledge,
                "knowledge_count": point.knowledge_count,
                "object_refs": point.object_refs,
                "observed_at": None if point.observed_at is None else point.observed_at.isoformat(),
                "screen_category": point.screen_category,
                "searchable_labels": point.searchable_labels,
                "semantic_summary": point.semantic_summary,
                "source_item_id": point.source_item_id,
                "vector": point.vector,
                "x": point.x,
                "y": point.y,
            }
            for point in sorted(points_by_id.values(), key=lambda point: point.source_item_id)
        ],
        "regions": [
            {
                "cluster_key": region.cluster_key,
                "item_source_item_ids": [item.source_item_id for item in sorted(region.items, key=lambda item: item.source_item_id)],
                "time_end": None if region.time_end is None else region.time_end.isoformat(),
                "time_start": None if region.time_start is None else region.time_start.isoformat(),
                "title": region.title,
                "top_apps": region.top_apps,
                "top_labels": region.top_labels,
                "x": region.x,
                "y": region.y,
            }
            for region in sorted(regions, key=lambda region: region.cluster_key)
        ],
    }
    corpus_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"atlas-input:semantic-map-run:{map_run_id}:{corpus_hash[:16]}", corpus_hash


def _embedding_version_from_dimension(dimension: int) -> str:
    return f"{dimension}d-basis"


def _ordered_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _tokenize_strings(values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_TOKEN_RE.findall(value.lower()))
    return tokens


def _cohesion_score(points: list[_AtlasPoint], centroid_vector: list[float]) -> float:
    if not points or not centroid_vector:
        return 0.0
    similarities = [_signal_similarity(point.vector, centroid_vector) for point in points]
    return round(sum(similarities) / len(similarities), 6)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


def _vector_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return dist(left, right)


def _compute_medoid_distances(items: list[AtlasCandidateItem]) -> dict[int, float]:
    return {
        item.source_item_id: sum(
            _vector_distance(item.vector, other.vector)
            for other in items
            if other.source_item_id != item.source_item_id
        )
        for item in items
    }


def _select_best_duplicate_candidates(
    items: list[AtlasCandidateItem],
    medoid_distances: dict[int, float],
) -> dict[tuple[str, ...], AtlasCandidateItem]:
    best_by_key: dict[tuple[str, ...], AtlasCandidateItem] = {}
    for item in items:
        existing = best_by_key.get(item.near_duplicate_key)
        if existing is None:
            best_by_key[item.near_duplicate_key] = item
            continue

        if _duplicate_preference_key(item, medoid_distances) < _duplicate_preference_key(existing, medoid_distances):
            best_by_key[item.near_duplicate_key] = item
    return best_by_key


def _duplicate_preference_key(
    item: AtlasCandidateItem,
    medoid_distances: dict[int, float],
) -> tuple[float, float, int]:
    return (
        medoid_distances[item.source_item_id],
        -item.metadata_score,
        item.source_item_id,
    )


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []

    summed = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            summed[index] += value
    return [value / len(vectors) for value in summed]


def _normalized_mean_vector(vectors: list[list[float]]) -> list[float]:
    return _normalize_vector(_mean_vector(vectors))


def _normalize_vector(vector: list[float]) -> list[float]:
    magnitude = _vector_magnitude(vector)
    if magnitude == 0.0:
        return [0.0] * len(vector)
    return [value / magnitude for value in vector]


def _vector_magnitude(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _principal_component(vectors: list[list[float]], *, dimension: int) -> list[float]:
    if not vectors:
        fallback = [0.0] * dimension
        fallback[0] = 1.0
        return fallback

    seed_index = _highest_variance_dimension(vectors)
    component = [0.0] * dimension
    component[seed_index] = 1.0
    for _ in range(24):
        candidate = [0.0] * dimension
        for vector in vectors:
            projection = sum(left * right for left, right in zip(vector, component))
            for index, value in enumerate(vector):
                candidate[index] += projection * value
        normalized = _normalize_vector(candidate)
        if _vector_magnitude(normalized) == 0.0:
            break
        component = normalized

    dominant_index = max(range(len(component)), key=lambda index: abs(component[index]))
    if component[dominant_index] < 0:
        component = [-value for value in component]
    return component


def _highest_variance_dimension(vectors: list[list[float]]) -> int:
    dimension = len(vectors[0])
    variances: list[tuple[float, int]] = []
    for index in range(dimension):
        values = [vector[index] for vector in vectors]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values)
        variances.append((variance, index))
    return max(variances)[1]


def _subtract_projection(vector: list[float], axis: list[float]) -> list[float]:
    projection = sum(left * right for left, right in zip(vector, axis))
    return [
        value - projection * axis[index]
        for index, value in enumerate(vector)
    ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= 1:
        return points

    ordered_points = sorted(points)

    def _cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return ((left[0] - origin[0]) * (right[1] - origin[1])) - (
            (left[1] - origin[1]) * (right[0] - origin[0])
        )

    lower: list[tuple[float, float]] = []
    for point in ordered_points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(ordered_points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def _signal_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((left_value - right_value) ** 2 for left_value, right_value in zip(left, right)))


def _signal_similarity(left: list[float], right: list[float]) -> float:
    return 1.0 / (1.0 + _signal_distance(left, right))


def _parse_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    return datetime.fromisoformat(raw_value)
