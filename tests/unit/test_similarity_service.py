from __future__ import annotations

import json
from datetime import datetime
from datetime import UTC

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import Base
from memoria.domain.models import Blob
from memoria.domain.models import SourceItem
from memoria.similarity.service import SimilarityGraphFilters
from memoria.similarity.service import get_similarity_graph


def test_build_similarity_graph_groups_nodes_by_category_and_filters_weak_edges() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_similarity_fixture(session)

        overview = get_similarity_graph(session, min_cluster_size=2, min_edge_weight=0.3)

    assert [node.region_key for node in overview.nodes] == ["region-a", "region-b"]
    assert [node.dominant_screen_category for node in overview.nodes] == ["social", "finance"]
    assert overview.legend[0].category == "social"
    assert overview.legend[0].count == 1
    assert [(edge.source_region_key, edge.target_region_key) for edge in overview.edges] == [
        ("region-a", "region-b")
    ]


def test_build_similarity_graph_keeps_snapshot_metadata_when_unfiltered() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_similarity_fixture(session)

        overview = get_similarity_graph(session, min_cluster_size=2, min_edge_weight=0.3)

    assert [node.region_key for node in overview.nodes] == ["region-a", "region-b"]
    assert overview.nodes[0].top_labels == ["chat", "friends", "whatsapp"]
    assert overview.nodes[0].top_apps == ["telegram", "whatsapp"]
    assert overview.nodes[0].top_entities == ["entity:alice", "entity:bob"]
    assert overview.nodes[0].representative_source_item_ids == [101, 103, 102]


def test_build_similarity_graph_applies_item_filters_to_node_selection_and_dominant_category() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_similarity_fixture(session)

        overview = get_similarity_graph(
            session,
            filters=SimilarityGraphFilters(app_hint="telegram", min_cluster_size=2),
        )

    assert [node.region_key for node in overview.nodes] == ["region-a"]
    assert overview.nodes[0].item_count == 2
    assert overview.nodes[0].size > 0
    assert overview.nodes[0].dominant_screen_category == "social"
    assert overview.nodes[0].top_labels == ["chat", "friends"]
    assert overview.nodes[0].top_apps == ["telegram"]
    assert overview.nodes[0].top_entities == ["alice"]
    assert overview.nodes[0].representative_source_item_ids == [101, 102]
    assert overview.nodes[0].top_labels != ["chat", "friends", "whatsapp"]
    assert overview.nodes[0].representative_source_item_ids != [101, 103, 102]
    assert [(entry.category, entry.color, entry.count) for entry in overview.legend] == [
        ("social", "#2EC4B6", 1)
    ]
    assert overview.edges == []


def test_build_similarity_graph_honors_explicit_zero_threshold_overrides() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_similarity_fixture(session)

        overview = get_similarity_graph(
            session,
            filters=SimilarityGraphFilters(min_cluster_size=5, min_edge_weight=0.8),
            min_cluster_size=0,
            min_edge_weight=0.0,
        )

    assert [node.region_key for node in overview.nodes] == ["region-a", "region-b", "region-c"]
    assert overview.filters.min_cluster_size == 0
    assert overview.filters.min_edge_weight == 0.0
    assert [(edge.source_region_key, edge.target_region_key) for edge in overview.edges] == [
        ("region-a", "region-b"),
        ("region-a", "region-c"),
    ]


def _seed_similarity_fixture(session: Session) -> None:
    atlas_run = AtlasRun(
        atlas_key="screenshots_atlas_v1",
        source_family="screenshot",
        status="completed",
        source_count=6,
        embedding_type="dense",
        embedding_model="test-model",
        embedding_version="1",
        clustering_method="test-clustering",
        clustering_params_json=json.dumps({"k": 3}),
        random_seed=42,
        layout_version="atlas-world-v1",
        created_at=datetime(2026, 4, 12, 9, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 12, 9, 5, tzinfo=UTC),
        published_at=datetime(2026, 4, 12, 9, 10, tzinfo=UTC),
    )
    session.add(atlas_run)
    session.flush()

    session.add_all(
        [
            AtlasRegion(
                atlas_run_id=atlas_run.id,
                region_key="region-a",
                parent_region_key=None,
                level=0,
                title="Social cluster",
                x=0.1,
                y=0.2,
                label_x=0.1,
                label_y=0.2,
                region_shape_json=json.dumps({"shape_type": "polygon", "rings": []}),
                item_count=3,
                top_labels_json=json.dumps(["chat", "friends", "whatsapp"]),
                top_apps_json=json.dumps(["telegram", "whatsapp"]),
                top_people_json=json.dumps([]),
                top_entities_json=json.dumps(["entity:alice", "entity:bob"]),
                representatives_json=json.dumps(
                    [
                        {"rank": 1, "source_item_id": 101},
                        {"rank": 2, "source_item_id": 103},
                        {"rank": 3, "source_item_id": 102},
                    ]
                ),
                bridge_neighbors_json=json.dumps([]),
                cohesion_score=0.9,
            ),
            AtlasRegion(
                atlas_run_id=atlas_run.id,
                region_key="region-b",
                parent_region_key=None,
                level=0,
                title="Finance cluster",
                x=0.6,
                y=0.4,
                label_x=0.6,
                label_y=0.4,
                region_shape_json=json.dumps({"shape_type": "polygon", "rings": []}),
                item_count=2,
                top_labels_json=json.dumps(["budget"]),
                top_apps_json=json.dumps(["sheets"]),
                top_people_json=json.dumps([]),
                top_entities_json=json.dumps(["entity:budget"]),
                representatives_json=json.dumps([{"rank": 1, "source_item_id": 201}]),
                bridge_neighbors_json=json.dumps([]),
                cohesion_score=0.8,
            ),
            AtlasRegion(
                atlas_run_id=atlas_run.id,
                region_key="region-c",
                parent_region_key=None,
                level=0,
                title="Tiny cluster",
                x=0.9,
                y=0.8,
                label_x=0.9,
                label_y=0.8,
                region_shape_json=json.dumps({"shape_type": "polygon", "rings": []}),
                item_count=1,
                top_labels_json=json.dumps(["single"]),
                top_apps_json=json.dumps(["notes"]),
                top_people_json=json.dumps([]),
                top_entities_json=json.dumps([]),
                representatives_json=json.dumps([{"rank": 1, "source_item_id": 301}]),
                bridge_neighbors_json=json.dumps([]),
                cohesion_score=0.7,
            ),
        ]
    )

    session.add_all(
        [
            AtlasEdge(
                atlas_run_id=atlas_run.id,
                source_region_key="region-a",
                target_region_key="region-b",
                weight=0.72,
                edge_type="semantic_similarity",
            ),
            AtlasEdge(
                atlas_run_id=atlas_run.id,
                source_region_key="region-a",
                target_region_key="region-c",
                weight=0.12,
                edge_type="semantic_similarity",
            ),
        ]
    )

    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=101,
        region_key="region-a",
        screen_category="social",
        app_hint="telegram",
        semantic_summary="chat with Alice about plans",
        object_refs=["topic:chat", "entity:alice"],
    )
    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=102,
        region_key="region-a",
        screen_category="social",
        app_hint="telegram",
        semantic_summary="friends planning thread",
        object_refs=["topic:friends", "entity:alice"],
    )
    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=103,
        region_key="region-a",
        screen_category="chat",
        app_hint="whatsapp",
        semantic_summary="whatsapp follow-up with Bob",
        object_refs=["topic:whatsapp", "entity:bob"],
    )
    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=201,
        region_key="region-b",
        screen_category="finance",
        app_hint="sheets",
    )
    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=202,
        region_key="region-b",
        screen_category="finance",
        app_hint="sheets",
    )
    _add_atlas_item(
        session,
        atlas_run_id=atlas_run.id,
        source_item_id=301,
        region_key="region-c",
        screen_category="notes",
        app_hint="notes",
    )
    session.commit()


def _add_atlas_item(
    session: Session,
    *,
    atlas_run_id: int,
    source_item_id: int,
    region_key: str,
    screen_category: str,
    app_hint: str,
    connector_instance_id: str = "similarity-test",
    has_knowledge: bool = False,
    observed_at: datetime | None = None,
    semantic_summary: str | None = None,
    object_refs: list[str] | None = None,
) -> None:
    blob = Blob(
        sha256=f"{source_item_id:064d}",
        media_type="image/png",
        byte_size=64,
        storage_kind="memory",
        storage_uri=f"memory://{source_item_id}",
    )
    session.add(blob)
    session.flush()

    session.add(
        SourceItem(
            id=source_item_id,
            source_type="screenshot",
            source_family="screenshot",
            connector_instance_id="similarity-test",
            external_id=f"ext-{source_item_id}",
            dedup_key=f"dedup-{source_item_id}",
            mode="absorb",
            status="ready",
            blob_id=blob.id,
        )
    )
    session.add(
        AtlasItem(
            atlas_run_id=atlas_run_id,
            source_item_id=source_item_id,
            region_key=region_key,
            subregion_key=None,
            x=0.0,
            y=0.0,
            semantic_summary=semantic_summary or f"summary-{source_item_id}",
            app_hint=app_hint,
            connector_instance_id=connector_instance_id,
            screen_category=screen_category,
            has_knowledge=has_knowledge,
            observed_at=observed_at or datetime(2026, 4, 12, 8, 0, tzinfo=UTC),
            object_refs_json=json.dumps(object_refs or []),
            is_representative=source_item_id in {101, 102, 201, 301},
            representative_rank=1 if source_item_id in {101, 201, 301} else 2 if source_item_id == 102 else None,
            is_bridge=False,
            bridge_type=None,
            secondary_region_key=None,
            bridge_score=0.0,
            screenshot_detail_url=f"/screenshots/{source_item_id}",
        )
    )
