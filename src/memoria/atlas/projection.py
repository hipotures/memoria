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
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import Embedding
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import PipelineRun
from memoria.domain.models import SemanticCluster
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourceItem
from memoria.search.embeddings import EMBEDDING_MODEL_NAME
from memoria.search.embeddings import embed_text

ATLAS_KEY = "screenshots_atlas_v1"
ATLAS_EMBEDDING_TYPE = "screenshot_semantic_text"
ATLAS_EMBEDDING_VERSION = "96d-basis"
ATLAS_CLUSTERING_METHOD = "semantic-map-plus-subregions-v1"
ATLAS_LAYOUT_VERSION = "atlas-world-v1"
ATLAS_RANDOM_SEED = 42
REGION_SHAPE_PADDING = 42.0
BRIDGE_MARGIN_THRESHOLD = 0.12
BRIDGE_SECONDARY_DISTANCE_THRESHOLD = 1.0
REGION_IDENTITY_OVERLAP_THRESHOLD = 0.6
REGION_IDENTITY_CENTROID_THRESHOLD = 0.2
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


@dataclass(slots=True)
class _LatestSemanticMapRun:
    map_run_id: int
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
        source_snapshot_id=f"semantic-map-run:{latest_map_run.map_run_id}",
        corpus_hash=_hash_source_ids(latest_map_run.source_item_ids),
        embedding_type=ATLAS_EMBEDDING_TYPE,
        embedding_model=EMBEDDING_MODEL_NAME,
        embedding_version=ATLAS_EMBEDDING_VERSION,
        clustering_method=ATLAS_CLUSTERING_METHOD,
        clustering_params_json=json.dumps(
            {
                "bridge_margin": BRIDGE_MARGIN_THRESHOLD,
                "subregion_cap": 8,
                "topology": "semantic-map-derived",
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

    map_points = session.scalars(
        select(SemanticMapPoint)
        .where(SemanticMapPoint.map_run_id == map_run.id)
        .order_by(SemanticMapPoint.id.asc())
    ).all()
    source_item_ids = [point.source_item_id for point in map_points]
    object_refs_by_source_item_id = _load_object_refs_by_source_item_id(
        session,
        source_item_ids=source_item_ids,
    )
    knowledge_counts_by_source_item_id = _load_knowledge_counts_by_source_item_id(
        session,
        source_item_ids=source_item_ids,
    )

    points_by_id: dict[int, _AtlasPoint] = {}
    grouped_points: dict[str, list[_AtlasPoint]] = defaultdict(list)
    for point in map_points:
        interpretation = session.get(AssetInterpretation, point.source_item_id)
        source_item = session.get(SourceItem, point.source_item_id)
        embedding = session.scalar(
            select(Embedding).where(
                Embedding.source_item_id == point.source_item_id,
                Embedding.embedding_type == ATLAS_EMBEDDING_TYPE,
            )
        )
        if interpretation is None or source_item is None or embedding is None or point.cluster_key is None:
            continue

        atlas_point = _AtlasPoint(
            source_item_id=point.source_item_id,
            cluster_key=point.cluster_key,
            x=point.x,
            y=point.y,
            vector=embed_text(embedding.content_text),
            semantic_summary=interpretation.semantic_summary,
            app_hint=interpretation.app_hint,
            observed_at=source_item.source_observed_at or source_item.source_created_at,
            object_refs=object_refs_by_source_item_id.get(point.source_item_id, []),
            knowledge_count=knowledge_counts_by_source_item_id.get(point.source_item_id, 0),
            searchable_labels=json.loads(interpretation.searchable_labels_json or "[]"),
            cluster_hints=json.loads(interpretation.cluster_hints_json or "[]"),
        )
        points_by_id[point.source_item_id] = atlas_point
        grouped_points[atlas_point.cluster_key].append(atlas_point)

    regions: list[_SemanticRegionSource] = []
    for cluster in clusters:
        summary = json.loads(cluster.summary_json or "{}")
        regions.append(
            _SemanticRegionSource(
                cluster_key=cluster.cluster_key,
                title=str(summary.get("title") or cluster.title or cluster.cluster_key),
                x=cluster.centroid_x,
                y=cluster.centroid_y,
                top_labels=list(summary.get("top_labels") or []),
                top_apps=list(summary.get("dominant_apps") or []),
                time_start=_parse_datetime(summary.get("time_start")),
                time_end=_parse_datetime(summary.get("time_end")),
                items=grouped_points.get(cluster.cluster_key, []),
            )
        )

    return _LatestSemanticMapRun(
        map_run_id=map_run.id,
        regions=[region for region in regions if region.items],
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
        centroid = _normalized_average(
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
    top_regions: list[_AtlasRegionDraft] = []
    for region_source in latest_map_run.regions:
        current_source_item_ids = {item.source_item_id for item in region_source.items}
        centroid_vector = _normalized_average([item.vector for item in region_source.items])
        top_summary = _summarize_points(region_source.items, fallback_title=region_source.title)
        region_key = match_region_identity(
            prior_regions=prior_region_identities,
            source_item_ids=current_source_item_ids,
            centroid=centroid_vector,
            label_tokens=_tokenize_strings([top_summary["title"], *top_summary["top_labels"]]),
        )
        if region_key is None:
            region_key = f"region-{region_source.cluster_key}"

        representative_rank_by_source_item_id = _representative_rank_by_source_item_id(region_source.items)
        subregions, subregion_key_by_source_item_id = _build_subregions(
            parent_region_key=region_key,
            items=region_source.items,
        )

        top_regions.append(
            _AtlasRegionDraft(
                region_key=region_key,
                parent_region_key=None,
                level=0,
                title=top_summary["title"],
                x=region_source.x,
                y=region_source.y,
                label_x=region_source.x,
                label_y=region_source.y,
                region_shape=_build_region_shape(region_source.items),
                item_count=len(region_source.items),
                top_labels=top_summary["top_labels"],
                top_apps=top_summary["top_apps"],
                top_people=top_summary["top_people"],
                top_entities=top_summary["top_entities"],
                time_start=top_summary["time_start"],
                time_end=top_summary["time_end"],
                representatives=_representatives_payload(representative_rank_by_source_item_id),
                bridge_neighbors=[],
                cohesion_score=_cohesion_score(region_source.items, centroid_vector),
                centroid_vector=centroid_vector,
                items=region_source.items,
                representative_rank_by_source_item_id=representative_rank_by_source_item_id,
                subregion_key_by_source_item_id=subregion_key_by_source_item_id,
                subregions=subregions,
            )
        )
    return top_regions


def _build_subregions(
    *,
    parent_region_key: str,
    items: list[_AtlasPoint],
) -> tuple[list[_AtlasRegionDraft], dict[int, str]]:
    subregion_count = min(derive_subregion_count(len(items)), len(items))
    if subregion_count <= 0:
        return [], {}

    center_x = sum(item.x for item in items) / len(items)
    center_y = sum(item.y for item in items) / len(items)
    ordered_items = sorted(
        items,
        key=lambda item: (
            math.atan2(item.y - center_y, item.x - center_x),
            item.source_item_id,
        ),
    )

    subregions: list[_AtlasRegionDraft] = []
    subregion_key_by_source_item_id: dict[int, str] = {}
    chunk_size = math.ceil(len(ordered_items) / subregion_count)
    for index in range(subregion_count):
        chunk = ordered_items[index * chunk_size : (index + 1) * chunk_size]
        if not chunk:
            continue

        chunk_summary = _summarize_points(
            chunk,
            fallback_title=f"{parent_region_key} / {index + 1}",
        )
        centroid_vector = _normalized_average([item.vector for item in chunk])
        chunk_x = round(sum(item.x for item in chunk) / len(chunk), 3)
        chunk_y = round(sum(item.y for item in chunk) / len(chunk), 3)
        subregion_key = f"{parent_region_key}/subregion-{index + 1:02d}"
        representative_rank_by_source_item_id = _representative_rank_by_source_item_id(chunk, limit=3)
        for item in chunk:
            subregion_key_by_source_item_id[item.source_item_id] = subregion_key

        subregions.append(
            _AtlasRegionDraft(
                region_key=subregion_key,
                parent_region_key=parent_region_key,
                level=1,
                title=chunk_summary["title"],
                x=chunk_x,
                y=chunk_y,
                label_x=chunk_x,
                label_y=chunk_y,
                region_shape=_build_region_shape(chunk, padding=24.0),
                item_count=len(chunk),
                top_labels=chunk_summary["top_labels"],
                top_apps=chunk_summary["top_apps"],
                top_people=chunk_summary["top_people"],
                top_entities=chunk_summary["top_entities"],
                time_start=chunk_summary["time_start"],
                time_end=chunk_summary["time_end"],
                representatives=_representatives_payload(representative_rank_by_source_item_id),
                bridge_neighbors=[],
                cohesion_score=_cohesion_score(chunk, centroid_vector),
                centroid_vector=centroid_vector,
                items=chunk,
                representative_rank_by_source_item_id=representative_rank_by_source_item_id,
                subregion_key_by_source_item_id={},
                subregions=[],
            )
        )

    return subregions, subregion_key_by_source_item_id


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

    for left_region, right_region in combinations(sorted(top_regions, key=lambda region: region.region_key), 2):
        semantic_weight = round(
            max(0.0, _cosine_similarity(left_region.centroid_vector, right_region.centroid_vector)),
            6,
        )
        edge_drafts.append(
            _AtlasEdgeDraft(
                source_region_key=left_region.region_key,
                target_region_key=right_region.region_key,
                weight=semantic_weight,
                edge_type="semantic_similarity",
            )
        )
        neighbors_by_region_key[left_region.region_key].append(
            {
                "edge_type": "semantic_similarity",
                "region_key": right_region.region_key,
                "weight": semantic_weight,
            }
        )
        neighbors_by_region_key[right_region.region_key].append(
            {
                "edge_type": "semantic_similarity",
                "region_key": left_region.region_key,
                "weight": semantic_weight,
            }
        )

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
    distances = sorted(
        (
            (1.0 - _cosine_similarity(point.vector, centroid), region_key)
            for region_key, centroid in region_centroids.items()
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    if len(distances) < 2:
        return None

    primary_distance, resolved_primary_region_key = distances[0]
    secondary_distance, secondary_region_key = distances[1]
    return classify_bridge(
        primary_region_key=primary_region_key if primary_region_key == resolved_primary_region_key else resolved_primary_region_key,
        secondary_region_key=secondary_region_key,
        primary_distance=primary_distance,
        secondary_distance=secondary_distance,
        same_parent=False,
    )


def _build_region_shape(
    points: list[_AtlasPoint],
    *,
    padding: float = REGION_SHAPE_PADDING,
) -> dict[str, object]:
    if not points:
        return {"rings": [], "shape_type": "polygon"}

    xs = [point.x for point in points]
    ys = [point.y for point in points]
    min_x = min(xs) - padding
    max_x = max(xs) + padding
    min_y = min(ys) - padding
    max_y = max(ys) + padding
    return {
        "shape_type": "polygon",
        "rings": [
            [
                {"x": round(min_x, 3), "y": round(min_y, 3)},
                {"x": round(max_x, 3), "y": round(min_y, 3)},
                {"x": round(max_x, 3), "y": round(max_y, 3)},
                {"x": round(min_x, 3), "y": round(max_y, 3)},
                {"x": round(min_x, 3), "y": round(min_y, 3)},
            ]
        ],
    }


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
    title = top_labels[0] if top_labels else fallback_title

    return {
        "title": title,
        "top_apps": top_apps,
        "top_entities": top_entities,
        "top_labels": top_labels,
        "top_people": top_people,
        "time_end": max(observed_values) if observed_values else None,
        "time_start": min(observed_values) if observed_values else None,
    }


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


def _hash_source_ids(source_item_ids: list[int]) -> str:
    digest = hashlib.sha256(",".join(str(source_item_id) for source_item_id in sorted(source_item_ids)).encode("utf-8"))
    return digest.hexdigest()


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
    similarities = [_cosine_similarity(point.vector, centroid_vector) for point in points]
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


def _normalized_average(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []

    summed = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            summed[index] += value
    magnitude = math.sqrt(sum(value * value for value in summed))
    if magnitude == 0.0:
        return [0.0] * len(summed)
    return [value / magnitude for value in summed]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _parse_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    return datetime.fromisoformat(raw_value)
