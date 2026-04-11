from __future__ import annotations

from math import dist
from typing import Sequence

from memoria.atlas.contracts import AtlasCandidateItem
from memoria.atlas.contracts import BridgeClassification
from memoria.atlas.contracts import PriorRegionIdentity

BRIDGE_MARGIN_THRESHOLD = 0.12
REGION_IDENTITY_OVERLAP_THRESHOLD = 0.6
REGION_IDENTITY_CENTROID_THRESHOLD = 0.2


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

    medoid_distances = {
        item.source_item_id: sum(
            _vector_distance(item.vector, other.vector)
            for other in items
            if other.source_item_id != item.source_item_id
        )
        for item in items
    }

    deduplicated_items = list(_select_best_duplicate_candidates(items, medoid_distances).values())

    ordered = sorted(
        deduplicated_items,
        key=lambda item: (
            medoid_distances[item.source_item_id],
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


def _vector_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return dist(left, right)


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
