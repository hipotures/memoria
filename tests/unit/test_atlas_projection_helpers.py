from __future__ import annotations

from memoria.atlas.contracts import AtlasCandidateItem
from memoria.atlas.contracts import PriorRegionIdentity
from memoria.atlas.projection import classify_bridge
from memoria.atlas.projection import derive_subregion_count
from memoria.atlas.projection import match_region_identity
from memoria.atlas.projection import select_representatives


def test_derive_subregion_count_scales_with_region_size() -> None:
    assert derive_subregion_count(4) == 0
    assert derive_subregion_count(18) == 3
    assert derive_subregion_count(65) == 6


def test_derive_subregion_count_respects_threshold_boundaries() -> None:
    assert derive_subregion_count(7) == 0
    assert derive_subregion_count(8) == 3
    assert derive_subregion_count(20) == 4
    assert derive_subregion_count(40) == 6
    assert derive_subregion_count(80) == 8


def test_select_representatives_prefers_medoid_then_metadata_quality() -> None:
    ranked = select_representatives(
        [
            AtlasCandidateItem(10, [0.0, 0.0], "thin", None, [], 0),
            AtlasCandidateItem(11, [0.1, 0.0], "rich summary", "telegram", ["topic:trip"], 2),
            AtlasCandidateItem(12, [0.05, 0.0], "rich summary", "telegram", ["topic:trip", "thread:berlin"], 3),
        ],
        limit=2,
    )

    assert [item.source_item_id for item in ranked] == [12, 11]


def test_select_representatives_skips_near_duplicates_deterministically() -> None:
    ranked = select_representatives(
        [
            AtlasCandidateItem(9, [0.1, 0.0], "shared summary", "telegram", ["thread:berlin"], 2),
            AtlasCandidateItem(7, [0.1, 0.0], "shared summary", "telegram", ["thread:berlin"], 1),
            AtlasCandidateItem(12, [0.2, 0.0], "other summary", "telegram", ["thread:rome"], 1),
        ],
        limit=3,
    )

    assert [item.source_item_id for item in ranked] == [9, 12]


def test_select_representatives_keeps_better_medoid_duplicate_over_metadata_rich_outlier() -> None:
    ranked = select_representatives(
        [
            AtlasCandidateItem(20, [0.0, 0.0], "shared summary", "telegram", ["thread:berlin"], 1),
            AtlasCandidateItem(21, [2.0, 0.0], "shared summary", "telegram", ["thread:berlin"], 3),
            AtlasCandidateItem(22, [0.05, 0.0], "other summary", "telegram", ["thread:rome"], 1),
            AtlasCandidateItem(23, [0.1, 0.0], "another summary", None, [], 0),
        ],
        limit=3,
    )

    representative_ids = {item.source_item_id for item in ranked}

    assert 20 in representative_ids
    assert 21 not in representative_ids


def test_classify_bridge_marks_small_primary_secondary_margin() -> None:
    classification = classify_bridge(
        primary_region_key="region-a",
        secondary_region_key="region-b",
        primary_distance=0.32,
        secondary_distance=0.38,
        same_parent=False,
    )

    assert classification is not None
    assert classification.bridge_type == "external_bridge"


def test_classify_bridge_returns_none_when_margin_is_too_large() -> None:
    classification = classify_bridge(
        primary_region_key="region-a",
        secondary_region_key="region-b",
        primary_distance=0.32,
        secondary_distance=0.5,
        same_parent=True,
    )

    assert classification is None


def test_match_region_identity_reuses_prior_key_when_overlap_is_strong() -> None:
    matched = match_region_identity(
        prior_regions=[PriorRegionIdentity("atlas-r1", {1, 2, 3, 4}, [0.1, 0.2])],
        source_item_ids={1, 2, 3, 5},
        centroid=[0.1, 0.22],
        label_tokens={"telegram", "travel"},
    )

    assert matched == "atlas-r1"


def test_match_region_identity_prefers_best_overlap_then_label_tie_breaker() -> None:
    matched = match_region_identity(
        prior_regions=[
            PriorRegionIdentity("atlas-r2", {1, 2, 3, 4}, [0.1, 0.2], {"work"}),
            PriorRegionIdentity("atlas-r1", {1, 2, 3, 4}, [0.1, 0.2], {"travel"}),
        ],
        source_item_ids={1, 2, 3, 5},
        centroid=[0.1, 0.2],
        label_tokens={"travel"},
    )

    assert matched == "atlas-r1"


def test_match_region_identity_returns_none_for_weak_overlap() -> None:
    matched = match_region_identity(
        prior_regions=[PriorRegionIdentity("atlas-r1", {1, 2, 3, 4}, [0.1, 0.2])],
        source_item_ids={1, 7, 8, 9},
        centroid=[0.1, 0.2],
        label_tokens={"travel"},
    )

    assert matched is None
