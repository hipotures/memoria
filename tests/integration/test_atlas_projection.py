from __future__ import annotations

import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.integration._screenshot_read_helpers import create_test_engine
from tests.integration._screenshot_read_helpers import seed_atlas_dataset


def test_rebuild_screenshot_atlas_persists_latest_published_run(tmp_path):
    from memoria.atlas.projection import rebuild_screenshot_atlas
    from memoria.domain.models import AtlasEdge
    from memoria.domain.models import AtlasItem
    from memoria.domain.models import AtlasRegion
    from memoria.domain.models import AtlasRun

    engine = create_test_engine(tmp_path, "atlas-rebuild.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    assert result["atlas_run_id"] >= 1
    assert result["region_count"] >= 2
    assert result["item_count"] == seeded.total_source_items
    assert result["top_region_keys"]

    with Session(engine) as session:
        atlas_run = session.scalar(select(AtlasRun).order_by(AtlasRun.id.desc()))
        assert atlas_run is not None
        regions = session.scalars(
            select(AtlasRegion)
            .where(AtlasRegion.atlas_run_id == atlas_run.id)
            .order_by(AtlasRegion.level.asc(), AtlasRegion.region_key.asc())
        ).all()
        items = session.scalars(
            select(AtlasItem)
            .where(AtlasItem.atlas_run_id == atlas_run.id)
            .order_by(AtlasItem.source_item_id.asc())
        ).all()
        edges = session.scalars(
            select(AtlasEdge)
            .where(AtlasEdge.atlas_run_id == atlas_run.id)
            .order_by(AtlasEdge.edge_type.asc(), AtlasEdge.source_region_key.asc())
        ).all()

    assert atlas_run.atlas_key == "screenshots_atlas_v1"
    assert atlas_run.source_family == "screenshot"
    assert atlas_run.source_snapshot_id.startswith(
        f"atlas-input:semantic-map-run:{seeded.semantic_map_run_id}:"
    )
    assert atlas_run.corpus_hash is not None
    assert len(atlas_run.corpus_hash) == 64
    assert atlas_run.embedding_type == "screenshot_semantic_text"
    assert atlas_run.embedding_model == "hashed-text-v1"
    assert atlas_run.embedding_version == "96d-basis"
    assert atlas_run.completed_at is not None
    assert atlas_run.published_at is not None
    assert len(regions) == result["region_count"]
    assert len(items) == result["item_count"]
    assert len(edges) >= 1
    assert any(region.level == 0 for region in regions)
    assert any(item.is_representative for item in items)
    assert any(item.is_bridge for item in items) or any(edge.edge_type == "semantic_similarity" for edge in edges)
    assert all(item.screenshot_detail_url == f"/screenshots/{item.source_item_id}" for item in items)
    assert all(item.connector_instance_id == "atlas-seed" for item in items)
    assert any(item.screen_category == "chat" for item in items)
    assert any(item.has_knowledge for item in items)
    assert any(not item.has_knowledge for item in items)


def test_rebuild_screenshot_atlas_reuses_prior_region_keys_when_shape_is_stable(tmp_path):
    from memoria.atlas.projection import rebuild_screenshot_atlas
    from memoria.domain.models import AtlasRun
    from memoria.domain.models import AtlasRegion

    engine = create_test_engine(tmp_path, "atlas-rebuild-stable.db")
    seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        first = rebuild_screenshot_atlas(session, force=True)
        session.commit()
        first_run = session.get(AtlasRun, int(first["atlas_run_id"]))

    with Session(engine) as session:
        second = rebuild_screenshot_atlas(session, force=True)
        session.commit()
        second_run = session.get(AtlasRun, int(second["atlas_run_id"]))

    assert first["top_region_keys"] == second["top_region_keys"]
    assert first_run is not None
    assert second_run is not None
    assert first_run.source_snapshot_id == second_run.source_snapshot_id
    assert first_run.corpus_hash == second_run.corpus_hash

    with Session(engine) as session:
        first_region_keys = session.scalars(
            select(AtlasRegion.region_key)
            .where(
                AtlasRegion.atlas_run_id == int(first["atlas_run_id"]),
                AtlasRegion.level == 0,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()
        second_region_keys = session.scalars(
            select(AtlasRegion.region_key)
            .where(
                AtlasRegion.atlas_run_id == int(second["atlas_run_id"]),
                AtlasRegion.level == 0,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()

    assert first_region_keys == second_region_keys


def test_rebuild_screenshot_atlas_keeps_cross_region_bridges_off_self_edges(
    tmp_path, monkeypatch
):
    from memoria.atlas import projection
    from memoria.domain.models import AtlasEdge
    from memoria.domain.models import AtlasItem

    engine = create_test_engine(tmp_path, "atlas-bridge-regression.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    def _atlas_point(
        *,
        source_item_id: int,
        cluster_key: str,
        x: float,
        y: float,
        vector: list[float],
        semantic_summary: str,
        app_hint: str,
    ):
        return projection._AtlasPoint(
            source_item_id=source_item_id,
            cluster_key=cluster_key,
            x=x,
            y=y,
            vector=vector,
            semantic_summary=semantic_summary,
            app_hint=app_hint,
            connector_instance_id="atlas-seed",
            screen_category="chat",
            has_knowledge=False,
            observed_at=None,
            object_refs=[],
            knowledge_count=0,
            searchable_labels=[cluster_key],
            cluster_hints=[cluster_key],
        )

    region_a_bridge_point = _atlas_point(
        source_item_id=seeded.travel_source_item_ids[0],
        cluster_key="cluster-a",
        x=-12.0,
        y=0.0,
        vector=[0.4, 0.6],
        semantic_summary="Bridge candidate assigned to cluster A.",
        app_hint="telegram",
    )
    region_a_anchor_point = _atlas_point(
        source_item_id=seeded.travel_source_item_ids[1],
        cluster_key="cluster-a",
        x=-18.0,
        y=6.0,
        vector=[0.2, 0.8],
        semantic_summary="Anchor screenshot for cluster A.",
        app_hint="telegram",
    )
    region_b_anchor_point = _atlas_point(
        source_item_id=seeded.finance_source_item_ids[0],
        cluster_key="cluster-b",
        x=16.0,
        y=0.0,
        vector=[0.55, 0.45],
        semantic_summary="Anchor screenshot for cluster B.",
        app_hint="slack",
    )

    fake_map_run = projection._LatestSemanticMapRun(
        map_run_id=seeded.semantic_map_run_id,
        source_snapshot_id=f"atlas-input:semantic-map-run:{seeded.semantic_map_run_id}:bridgefixture",
        corpus_hash="bridgefixture",
        regions=[
            projection._SemanticRegionSource(
                cluster_key="cluster-a",
                title="Cluster A",
                x=-15.0,
                y=0.0,
                top_labels=["cluster-a"],
                top_apps=["telegram"],
                time_start=None,
                time_end=None,
                items=[region_a_bridge_point, region_a_anchor_point],
            ),
            projection._SemanticRegionSource(
                cluster_key="cluster-b",
                title="Cluster B",
                x=15.0,
                y=0.0,
                top_labels=["cluster-b"],
                top_apps=["slack"],
                time_start=None,
                time_end=None,
                items=[region_b_anchor_point],
            ),
        ],
        points_by_id={
            region_a_bridge_point.source_item_id: region_a_bridge_point,
            region_a_anchor_point.source_item_id: region_a_anchor_point,
            region_b_anchor_point.source_item_id: region_b_anchor_point,
        },
        embedding_type="screenshot_semantic_text",
        embedding_model="bridge-test-model",
        embedding_version="2d-basis",
    )

    monkeypatch.setattr(projection, "_load_latest_semantic_map_run", lambda session: fake_map_run)
    monkeypatch.setattr(
        projection,
        "_load_prior_region_identities",
        lambda session, *, points_by_id: [],
    )

    with Session(engine) as session:
        result = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        bridge_item = session.scalar(
            select(AtlasItem).where(
                AtlasItem.atlas_run_id == int(result["atlas_run_id"]),
                AtlasItem.source_item_id == region_a_bridge_point.source_item_id,
            )
        )
        bridge_edges = session.scalars(
            select(AtlasEdge)
            .where(
                AtlasEdge.atlas_run_id == int(result["atlas_run_id"]),
                AtlasEdge.edge_type == "semantic_bridge",
            )
            .order_by(AtlasEdge.source_region_key.asc(), AtlasEdge.target_region_key.asc())
        ).all()

    assert bridge_item is not None
    assert bridge_item.region_key == "region-cluster-a"
    assert bridge_item.secondary_region_key == "region-cluster-b"
    assert bridge_item.is_bridge is True
    assert bridge_edges
    assert all(edge.source_region_key != edge.target_region_key for edge in bridge_edges)
    assert {(edge.source_region_key, edge.target_region_key) for edge in bridge_edges} == {
        ("region-cluster-a", "region-cluster-b")
    }


def test_rebuild_screenshot_atlas_keeps_semantic_map_clusters_as_top_regions(
    tmp_path, monkeypatch
):
    from memoria.atlas import projection
    from memoria.domain.models import AtlasItem
    from memoria.domain.models import AtlasRegion

    engine = create_test_engine(tmp_path, "atlas-macroregions.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    def _atlas_point(
        *,
        source_item_id: int,
        cluster_key: str,
        x: float,
        y: float,
        vector: list[float],
        semantic_summary: str,
        app_hint: str,
        labels: list[str],
    ):
        return projection._AtlasPoint(
            source_item_id=source_item_id,
            cluster_key=cluster_key,
            x=x,
            y=y,
            vector=vector,
            semantic_summary=semantic_summary,
            app_hint=app_hint,
            connector_instance_id="atlas-seed",
            screen_category="chat",
            has_knowledge=False,
            observed_at=None,
            object_refs=[],
            knowledge_count=0,
            searchable_labels=labels,
            cluster_hints=labels,
        )

    cluster_specs = [
        (
            "cluster-travel-a",
            220.0,
            0.0,
            [
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[0],
                    cluster_key="cluster-travel-a",
                    x=220.0,
                    y=0.0,
                    vector=[1.0, 0.0],
                    semantic_summary="Travel planning: trains and hotel.",
                    app_hint="telegram",
                    labels=["travel", "trains"],
                ),
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[1],
                    cluster_key="cluster-travel-a",
                    x=228.0,
                    y=6.0,
                    vector=[0.98, 0.02],
                    semantic_summary="Travel planning: museum passes and itinerary.",
                    app_hint="telegram",
                    labels=["travel", "itinerary"],
                ),
            ],
        ),
        (
            "cluster-finance-a",
            110.0,
            190.0,
            [
                _atlas_point(
                    source_item_id=seeded.finance_source_item_ids[0],
                    cluster_key="cluster-finance-a",
                    x=110.0,
                    y=190.0,
                    vector=[0.0, 1.0],
                    semantic_summary="Finance ops: budget close and approvals.",
                    app_hint="slack",
                    labels=["finance", "budget"],
                ),
            ],
        ),
        (
            "cluster-travel-b",
            -110.0,
            190.0,
            [
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[2],
                    cluster_key="cluster-travel-b",
                    x=-110.0,
                    y=190.0,
                    vector=[0.97, 0.08],
                    semantic_summary="Travel logistics: platform and hostel.",
                    app_hint="whatsapp",
                    labels=["travel", "hostel"],
                ),
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[3],
                    cluster_key="cluster-travel-b",
                    x=-102.0,
                    y=198.0,
                    vector=[0.96, 0.1],
                    semantic_summary="Travel logistics: station arrival.",
                    app_hint="maps",
                    labels=["travel", "arrival"],
                ),
            ],
        ),
        (
            "cluster-finance-b",
            -220.0,
            0.0,
            [
                _atlas_point(
                    source_item_id=seeded.finance_source_item_ids[1],
                    cluster_key="cluster-finance-b",
                    x=-220.0,
                    y=0.0,
                    vector=[0.04, 0.98],
                    semantic_summary="Finance ops: variance review spreadsheet.",
                    app_hint="sheets",
                    labels=["finance", "variance"],
                ),
            ],
        ),
        (
            "cluster-travel-c",
            -110.0,
            -190.0,
            [
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[4],
                    cluster_key="cluster-travel-c",
                    x=-110.0,
                    y=-190.0,
                    vector=[0.95, -0.05],
                    semantic_summary="Travel review: bookings and departures.",
                    app_hint="gmail",
                    labels=["travel", "bookings"],
                ),
                _atlas_point(
                    source_item_id=seeded.travel_source_item_ids[5],
                    cluster_key="cluster-travel-c",
                    x=-116.0,
                    y=-182.0,
                    vector=[0.94, -0.08],
                    semantic_summary="Travel checklist: packing and passports.",
                    app_hint="calendar",
                    labels=["travel", "packing"],
                ),
            ],
        ),
        (
            "cluster-finance-c",
            110.0,
            -190.0,
            [
                _atlas_point(
                    source_item_id=seeded.finance_source_item_ids[2],
                    cluster_key="cluster-finance-c",
                    x=110.0,
                    y=-190.0,
                    vector=[-0.02, 0.97],
                    semantic_summary="Finance ops: expense reports and invoices.",
                    app_hint="gmail",
                    labels=["finance", "invoices"],
                ),
            ],
        ),
    ]

    fake_map_run = projection._LatestSemanticMapRun(
        map_run_id=seeded.semantic_map_run_id,
        source_snapshot_id=f"atlas-input:semantic-map-run:{seeded.semantic_map_run_id}:macrofixture",
        corpus_hash="macrofixture",
        embedding_type="screenshot_semantic_text",
        embedding_model="macro-test-model",
        embedding_version="2d-basis",
        regions=[
            projection._SemanticRegionSource(
                cluster_key=cluster_key,
                title=cluster_key,
                x=x,
                y=y,
                top_labels=[cluster_key],
                top_apps=[],
                time_start=None,
                time_end=None,
                items=items,
            )
            for cluster_key, x, y, items in cluster_specs
        ],
        points_by_id={
            point.source_item_id: point
            for _cluster_key, _x, _y, items in cluster_specs
            for point in items
        },
    )

    monkeypatch.setattr(projection, "_load_latest_semantic_map_run", lambda session: fake_map_run)
    monkeypatch.setattr(
        projection,
        "_load_prior_region_identities",
        lambda session, *, points_by_id: [],
    )

    with Session(engine) as session:
        result = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        top_regions = session.scalars(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == int(result["atlas_run_id"]),
                AtlasRegion.level == 0,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()
        subregions = session.scalars(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == int(result["atlas_run_id"]),
                AtlasRegion.level == 1,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()
        items = session.scalars(
            select(AtlasItem)
            .where(AtlasItem.atlas_run_id == int(result["atlas_run_id"]))
            .order_by(AtlasItem.source_item_id.asc())
        ).all()

    assert len(top_regions) == len(cluster_specs)
    assert subregions == []

    expected_region_keys = {
        f"region-{cluster_key}"
        for cluster_key, _x, _y, _items in cluster_specs
    }
    assert {region.region_key for region in top_regions} == expected_region_keys

    expected_region_key_by_source_item_id = {
        point.source_item_id: f"region-{cluster_key}"
        for cluster_key, _x, _y, cluster_items in cluster_specs
        for point in cluster_items
    }
    region_key_by_source_item_id = {
        item.source_item_id: item.region_key
        for item in items
    }
    assert region_key_by_source_item_id == expected_region_key_by_source_item_id


def test_rebuild_screenshot_atlas_keeps_semantic_map_snapshot_stable_when_embedding_rows_change(
    tmp_path
):
    from memoria.atlas import projection
    from memoria.domain.models import AtlasEdge
    from memoria.domain.models import AtlasRun
    from memoria.domain.models import Embedding
    from memoria.domain.models import SemanticMapRun

    engine = create_test_engine(tmp_path, "atlas-snapshot-metadata.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        first = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        semantic_map_run = session.scalar(select(SemanticMapRun).order_by(SemanticMapRun.id.desc()))
        assert semantic_map_run is not None
        semantic_map_config = json.loads(semantic_map_run.config_json)
        first_run = session.get(AtlasRun, int(first["atlas_run_id"]))
        first_edges = {
            (edge.source_region_key, edge.target_region_key): edge.weight
            for edge in session.scalars(
                select(AtlasEdge)
                .where(
                    AtlasEdge.atlas_run_id == int(first["atlas_run_id"]),
                    AtlasEdge.edge_type == "semantic_similarity",
                )
                .order_by(AtlasEdge.source_region_key.asc(), AtlasEdge.target_region_key.asc())
            ).all()
        }

    assert semantic_map_config["embedding_type"] == "screenshot_semantic_text"
    assert semantic_map_config["embedding_model"] == "hashed-text-v1"
    assert semantic_map_config["embedding_version"] == "96d-basis"
    assert semantic_map_config["embedding_dimension"] == 96
    assert first_run is not None

    with Session(engine) as session:
        embedding_rows = session.scalars(
            select(Embedding)
            .where(Embedding.source_item_id.in_(seeded.source_item_ids))
            .order_by(Embedding.id.asc())
        ).all()
        assert embedding_rows
        for embedding_row in embedding_rows:
            if embedding_row.source_item_id in seeded.travel_source_item_ids:
                embedding_row.content_text = "travel snapshot drift " * 24
            else:
                embedding_row.content_text = "finance snapshot drift " * 24
            embedding_row.model_name = "snapshot-test-model"
        session.commit()

    with Session(engine) as session:
        result = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        atlas_run = session.get(AtlasRun, int(result["atlas_run_id"]))
        second_edges = {
            (edge.source_region_key, edge.target_region_key): edge.weight
            for edge in session.scalars(
                select(AtlasEdge)
                .where(
                    AtlasEdge.atlas_run_id == int(result["atlas_run_id"]),
                    AtlasEdge.edge_type == "semantic_similarity",
                )
                .order_by(AtlasEdge.source_region_key.asc(), AtlasEdge.target_region_key.asc())
            ).all()
        }

    assert atlas_run is not None
    assert atlas_run.embedding_type == "screenshot_semantic_text"
    assert atlas_run.embedding_model == "hashed-text-v1"
    assert atlas_run.embedding_version == "96d-basis"
    assert atlas_run.source_snapshot_id == first_run.source_snapshot_id
    assert atlas_run.corpus_hash == first_run.corpus_hash
    assert second_edges == first_edges


def test_rebuild_screenshot_atlas_keeps_top_level_semantic_similarity_sparse_on_real_output(
    tmp_path
):
    from memoria.atlas.projection import rebuild_screenshot_atlas
    from memoria.domain.models import AtlasEdge
    from memoria.domain.models import AtlasRegion
    from memoria.domain.models import SemanticCluster
    from memoria.domain.models import SemanticMapRun

    engine = create_test_engine(tmp_path, "atlas-sparse-topology.db")
    seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        result = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        top_regions = session.scalars(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == int(result["atlas_run_id"]),
                AtlasRegion.level == 0,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()
        subregions = session.scalars(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == int(result["atlas_run_id"]),
                AtlasRegion.level == 1,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()
        latest_map_run_id = session.scalar(
            select(SemanticMapRun.id).order_by(SemanticMapRun.id.desc())
        )
        assert latest_map_run_id is not None
        semantic_cluster_count = len(
            session.scalars(
                select(SemanticCluster)
                .where(SemanticCluster.map_run_id == latest_map_run_id)
                .order_by(SemanticCluster.id.asc())
            ).all()
        )
        semantic_edges = session.scalars(
            select(AtlasEdge)
            .where(
                AtlasEdge.atlas_run_id == int(result["atlas_run_id"]),
                AtlasEdge.edge_type == "semantic_similarity",
            )
            .order_by(AtlasEdge.source_region_key.asc(), AtlasEdge.target_region_key.asc())
        ).all()

    assert len(top_regions) >= 2
    assert len(top_regions) == semantic_cluster_count
    assert subregions == []
    full_graph_edge_count = len(top_regions) * (len(top_regions) - 1) // 2
    assert 0 < len(semantic_edges) <= full_graph_edge_count
    if len(top_regions) > 2:
        assert len(semantic_edges) < full_graph_edge_count
    assert len(semantic_edges) <= len(top_regions) * 2


def test_rebuild_screenshot_atlas_populates_generated_subregion_bridge_neighbors(tmp_path, monkeypatch):
    from memoria.atlas import projection
    from memoria.domain.models import AtlasRegion

    engine = create_test_engine(tmp_path, "atlas-subregion-bridges.db")
    seeded = seed_atlas_dataset(engine, tmp_path)

    def _atlas_point(
        *,
        source_item_id: int,
        angle_index: int,
    ):
        angle = (math.pi * 2 * angle_index) / 9
        return projection._AtlasPoint(
            source_item_id=source_item_id,
            cluster_key="cluster-ops",
            x=round(math.cos(angle) * 100, 3),
            y=round(math.sin(angle) * 100, 3),
            vector=[
                0.995 if angle_index < 3 else 0.985 if angle_index < 6 else 0.975,
                0.01 if angle_index < 3 else 0.03 if angle_index < 6 else -0.02,
            ],
            semantic_summary=f"Operations capture {angle_index + 1}",
            app_hint="slack" if angle_index % 2 == 0 else "gmail",
            connector_instance_id="atlas-seed",
            screen_category="chat",
            has_knowledge=angle_index % 3 == 0,
            observed_at=None,
            object_refs=["topic:ops-review"],
            knowledge_count=1 if angle_index % 3 == 0 else 0,
            searchable_labels=["operations", "review"],
            cluster_hints=["operations review", f"lane {angle_index + 1}"],
        )

    region_points = [
        _atlas_point(source_item_id=source_item_id, angle_index=index)
        for index, source_item_id in enumerate(seeded.source_item_ids[:9])
    ]
    fake_map_run = projection._LatestSemanticMapRun(
        map_run_id=seeded.semantic_map_run_id,
        source_snapshot_id=f"atlas-input:semantic-map-run:{seeded.semantic_map_run_id}:subregionfixture",
        corpus_hash="subregionfixture",
        embedding_type="screenshot_semantic_text",
        embedding_model="subregion-test-model",
        embedding_version="2d-basis",
        regions=[
            projection._SemanticRegionSource(
                cluster_key="cluster-ops",
                title="cluster-ops",
                x=0.0,
                y=0.0,
                top_labels=["cluster-ops"],
                top_apps=["slack", "gmail"],
                time_start=None,
                time_end=None,
                items=region_points,
            )
        ],
        points_by_id={point.source_item_id: point for point in region_points},
    )

    monkeypatch.setattr(projection, "_load_latest_semantic_map_run", lambda session: fake_map_run)
    monkeypatch.setattr(
        projection,
        "_load_prior_region_identities",
        lambda session, *, points_by_id: [],
    )

    with Session(engine) as session:
        result = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        subregions = session.scalars(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == int(result["atlas_run_id"]),
                AtlasRegion.level == 1,
            )
            .order_by(AtlasRegion.region_key.asc())
        ).all()

    assert len(subregions) == 3
    subregion_keys = {region.region_key for region in subregions}

    for subregion in subregions:
        neighbors = json.loads(subregion.bridge_neighbors_json)
        assert neighbors
        assert {
            neighbor["region_key"]
            for neighbor in neighbors
        } <= (subregion_keys - {subregion.region_key})


def test_rebuild_screenshot_atlas_changes_snapshot_identity_when_live_metadata_changes(tmp_path):
    from memoria.atlas import projection
    from memoria.domain.models import AssetInterpretation
    from memoria.domain.models import AtlasItem
    from memoria.domain.models import AtlasRun

    engine = create_test_engine(tmp_path, "atlas-live-provenance.db")
    seeded = seed_atlas_dataset(engine, tmp_path)
    mutated_source_item_id = seeded.travel_source_item_ids[0]

    with Session(engine) as session:
        first = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()
        first_run = session.get(AtlasRun, int(first["atlas_run_id"]))

    assert first_run is not None

    with Session(engine) as session:
        interpretation = session.get(AssetInterpretation, mutated_source_item_id)
        assert interpretation is not None
        interpretation.semantic_summary = "Updated after the map snapshot but before atlas rebuild."
        session.commit()

    with Session(engine) as session:
        second = projection.rebuild_screenshot_atlas(session, force=True)
        session.commit()
        second_run = session.get(AtlasRun, int(second["atlas_run_id"]))
        mutated_item = session.scalar(
            select(AtlasItem).where(
                AtlasItem.atlas_run_id == int(second["atlas_run_id"]),
                AtlasItem.source_item_id == mutated_source_item_id,
            )
        )

    assert second_run is not None
    assert mutated_item is not None
    assert second_run.source_snapshot_id.startswith(
        f"atlas-input:semantic-map-run:{seeded.semantic_map_run_id}:"
    )
    assert second_run.source_snapshot_id != first_run.source_snapshot_id
    assert second_run.corpus_hash != first_run.corpus_hash
    assert mutated_item.semantic_summary == "Updated after the map snapshot but before atlas rebuild."
