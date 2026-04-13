from __future__ import annotations

from memoria.atlas.contracts import AtlasCandidateItem
from memoria.atlas.contracts import PriorRegionIdentity
from memoria.atlas.projection import _AtlasPoint
from memoria.atlas.projection import _compute_label_anchor
from memoria.atlas.projection import _summarize_points
from memoria.atlas.projection import classify_bridge
from memoria.atlas.projection import derive_subregion_count
from memoria.atlas.projection import match_region_identity
from memoria.atlas.projection import select_representatives


def _make_point(
    *,
    cluster_hints: list[str] | None = None,
    app_hint: str | None = None,
) -> _AtlasPoint:
    return _AtlasPoint(
        source_item_id=1,
        cluster_key="cluster-a",
        x=0.0,
        y=0.0,
        vector=[1.0, 0.0],
        semantic_summary="summary",
        app_hint=app_hint,
        connector_instance_id="test",
        screen_category="chat",
        has_knowledge=False,
        observed_at=None,
        object_refs=[],
        knowledge_count=0,
        searchable_labels=[],
        cluster_hints=cluster_hints or [],
    )


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


def test_select_representatives_ranks_survivors_using_deduplicated_medoid_scores() -> None:
    ranked = select_representatives(
        [
            AtlasCandidateItem(10, [0.0, 0.0], "left anchor", "telegram", ["thread:left"], 1),
            AtlasCandidateItem(20, [1.0, 0.0], "true medoid", "telegram", ["thread:center"], 1),
            AtlasCandidateItem(30, [3.0, 0.0], "duplicate cluster", "telegram", ["thread:right"], 1),
            AtlasCandidateItem(31, [3.0, 0.0], "duplicate cluster", "telegram", ["thread:right"], 1),
            AtlasCandidateItem(32, [3.0, 0.0], "duplicate cluster", "telegram", ["thread:right"], 1),
            AtlasCandidateItem(33, [3.0, 0.0], "duplicate cluster", "telegram", ["thread:right"], 1),
        ],
        limit=3,
    )

    ranked_ids = [item.source_item_id for item in ranked]

    assert ranked_ids[0] == 20
    assert 30 in ranked_ids


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


def test_classify_bridge_returns_none_when_secondary_affinity_is_too_weak() -> None:
    classification = classify_bridge(
        primary_region_key="region-a",
        secondary_region_key="region-b",
        primary_distance=10.0,
        secondary_distance=10.05,
        same_parent=False,
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


def test_build_region_title_prefers_semantic_label_over_generic_platform() -> None:
    summary = _summarize_points(
        [
            _make_point(cluster_hints=["chrome", "dns management"], app_hint="chrome"),
            _make_point(cluster_hints=["chrome", "dns management"], app_hint="chrome"),
        ],
        fallback_title="cluster-001",
    )

    assert summary["title"] == "chrome · dns management"


def test_build_region_title_falls_back_to_two_semantic_labels_without_app() -> None:
    summary = _summarize_points(
        [
            _make_point(cluster_hints=["delivery status", "refund tracking"], app_hint=None),
            _make_point(cluster_hints=["delivery status", "refund tracking"], app_hint=None),
        ],
        fallback_title="cluster-002",
    )

    assert summary["title"] == "delivery status, refund tracking"


def test_compute_label_anchor_offsets_from_region_center() -> None:
    anchor_x, anchor_y = _compute_label_anchor(
        region_x=40.0,
        region_y=50.0,
        region_shape={
            "shape_type": "polygon",
            "rings": [[
                {"x": 35.0, "y": 45.0},
                {"x": 45.0, "y": 45.0},
                {"x": 45.0, "y": 55.0},
                {"x": 35.0, "y": 55.0},
            ]],
        },
        atlas_center=(50.0, 50.0),
    )

    assert anchor_x > 40.0
    assert anchor_y < 50.0
    assert anchor_x - 40.0 >= 3.0
    assert 50.0 - anchor_y >= 3.0
