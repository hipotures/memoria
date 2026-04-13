from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import memoria.api.app as api_app_module
from memoria.api.app import create_app
from memoria.domain.models import AtlasEdge
from memoria.domain.models import AtlasItem
from memoria.domain.models import AtlasRegion
from memoria.domain.models import AtlasRun
from memoria.domain.models import Blob
from memoria.domain.models import SourceItem
from tests.integration._screenshot_read_helpers import create_test_engine


def test_similarity_graph_endpoint_returns_nodes_edges_and_legend(tmp_path: Path) -> None:
    client, engine = _create_test_client(tmp_path, "similarity-graph.db")
    _seed_similarity_fixture(engine)

    response = client.get("/similarity/graph", params={"min_cluster_size": 2, "min_edge_weight": 0.25})

    assert response.status_code == 200
    payload = response.json()
    nodes_by_region = {node["region_key"]: node for node in payload["nodes"]}
    legend_by_category = {entry["category"]: entry for entry in payload["legend"]}
    assert payload["run"]["atlas_key"] == "screenshots_atlas_v1"
    assert nodes_by_region["region-social"]["dominant_screen_category"] == "social"
    assert payload["edges"][0]["reason"] == "semantic_similarity"
    assert legend_by_category["social"]["count"] == 1
    assert payload["filters"] == {
        "connector_instance_id": None,
        "app_hint": None,
        "screen_category": None,
        "has_knowledge": None,
        "observed_from": None,
        "observed_to": None,
        "search_query": None,
        "min_cluster_size": 2,
        "min_edge_weight": 0.25,
    }


def test_similarity_graph_endpoint_reports_graph_kind_edge_scope_and_render_labels(
    tmp_path: Path,
) -> None:
    client, engine = _create_test_client(tmp_path, "similarity-graph-shape.db")
    _seed_similarity_fixture(engine)

    response = client.get("/similarity/graph")

    assert response.status_code == 200
    payload = response.json()
    nodes_by_region = {node["region_key"]: node for node in payload["nodes"]}
    assert payload["graph_kind"] == "region_similarity"
    assert payload["edge_scope"] == "atlas_snapshot"
    assert nodes_by_region["region-social"]["label"] == "Social region"
    assert nodes_by_region["region-social"]["canonical_title"] == "social region"
    assert nodes_by_region["region-social"]["duplicate_title_count"] == 1
    assert nodes_by_region["region-social"]["degree"] == 1
    assert nodes_by_region["region-social"]["label_priority"] == 6.0
    assert nodes_by_region["region-social"]["is_labeled"] is True
    assert nodes_by_region["region-social"]["label_x"] != nodes_by_region["region-social"]["x"] or (
        nodes_by_region["region-social"]["label_y"] != nodes_by_region["region-social"]["y"]
    )
    assert payload["edges"][0]["edge_type"] == "semantic_similarity"
    assert payload["edges"][0]["reason"] == "semantic_similarity"


def test_similarity_page_returns_fallback_html_when_frontend_build_is_missing(tmp_path: Path) -> None:
    client, _ = _create_test_client(
        tmp_path,
        "similarity-page-fallback.db",
        similarity_frontend_dist_dir=tmp_path / "missing-similarity-dist",
    )

    response = client.get("/similarity")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Atlas region similarity graph frontend build is not present" in response.text
    assert "/similarity/graph" in response.text


def test_similarity_page_serves_built_frontend_and_bundle_assets(tmp_path: Path) -> None:
    frontend_dist_dir = _create_fake_frontend_dist(tmp_path)
    client, _ = _create_test_client(
        tmp_path,
        "similarity-page-built.db",
        similarity_frontend_dist_dir=frontend_dist_dir,
    )

    page_response = client.get("/similarity")
    script_response = client.get("/similarity/assets/app.js")
    style_response = client.get("/similarity/assets/app.css")

    assert page_response.status_code == 200
    assert "Similarity graph frontend build is not present" not in page_response.text
    assert "/similarity/assets/app.js" in page_response.text
    assert "/similarity/assets/app.css" in page_response.text

    assert script_response.status_code == 200
    assert "text/javascript" in script_response.headers["content-type"]
    assert "similarity bundle loaded" in script_response.text

    assert style_response.status_code == 200
    assert "text/css" in style_response.headers["content-type"]
    assert "background" in style_response.text


def test_similarity_page_rewrites_assets_with_root_path_prefix(tmp_path: Path) -> None:
    frontend_dist_dir = _create_fake_frontend_dist(tmp_path)
    client, _ = _create_test_client(
        tmp_path,
        "similarity-root-path.db",
        similarity_frontend_dist_dir=frontend_dist_dir,
        root_path="/proxy-prefix",
    )

    response = client.get("/similarity")

    assert response.status_code == 200
    assert 'href="/proxy-prefix/similarity/assets/app.css"' in response.text
    assert 'src="/proxy-prefix/similarity/assets/app.js"' in response.text


def test_similarity_create_test_client_uses_stub_runtime_engines(tmp_path: Path, monkeypatch) -> None:
    def _unexpected_runtime_engine(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("runtime engine factory should not be called in similarity route tests")

    monkeypatch.setattr(api_app_module, "create_ocr_engine", _unexpected_runtime_engine)
    monkeypatch.setattr(api_app_module, "create_vision_engine", _unexpected_runtime_engine)

    client, _ = _create_test_client(tmp_path, "similarity-stub-engines.db")

    response = client.get("/similarity")

    assert response.status_code == 200


def _create_test_client(
    tmp_path: Path,
    database_name: str,
    *,
    similarity_frontend_dist_dir: Path | None = None,
    root_path: str = "",
) -> tuple[TestClient, object]:
    engine = create_test_engine(tmp_path, database_name)
    app = create_app(
        database_url=f"sqlite:///{tmp_path / database_name}",
        blob_dir=tmp_path / "blobs",
        similarity_frontend_dist_dir=similarity_frontend_dist_dir,
        ocr_engine=_UnusedOcrEngine(),
        vision_engine=_UnusedVisionEngine(),
    )
    return TestClient(app, root_path=root_path), engine


def _seed_similarity_fixture(engine: object) -> None:
    with Session(engine) as session:
        atlas_run = AtlasRun(
            atlas_key="screenshots_atlas_v1",
            source_family="screenshot",
            status="completed",
            source_count=5,
            embedding_type="dense",
            embedding_model="test-model",
            embedding_version="1",
            clustering_method="test-clustering",
            clustering_params_json=json.dumps({"k": 2}),
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
                    region_key="region-social",
                    parent_region_key=None,
                    level=0,
                    title="Social region",
                    x=0.1,
                    y=0.2,
                    label_x=0.16,
                    label_y=0.24,
                    region_shape_json=json.dumps({"shape_type": "polygon", "rings": []}),
                    item_count=3,
                    top_labels_json=json.dumps(["chat", "friends", "whatsapp"]),
                    top_apps_json=json.dumps(["telegram", "whatsapp"]),
                    top_people_json=json.dumps([]),
                    top_entities_json=json.dumps(["entity:alice", "entity:bob"]),
                    representatives_json=json.dumps(
                        [
                            {"rank": 1, "source_item_id": 101},
                            {"rank": 2, "source_item_id": 102},
                        ]
                    ),
                    bridge_neighbors_json=json.dumps([]),
                    cohesion_score=0.9,
                ),
                AtlasRegion(
                    atlas_run_id=atlas_run.id,
                    region_key="region-finance",
                    parent_region_key=None,
                    level=0,
                    title="Finance region",
                    x=0.7,
                    y=0.4,
                    label_x=0.74,
                    label_y=0.46,
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
            ]
        )
        session.flush()
        session.add(
            AtlasEdge(
                atlas_run_id=atlas_run.id,
                source_region_key="region-social",
                target_region_key="region-finance",
                weight=0.72,
                edge_type="semantic_similarity",
            )
        )

        _add_atlas_item(
            session,
            atlas_run_id=atlas_run.id,
            source_item_id=101,
            region_key="region-social",
            screen_category="social",
            app_hint="telegram",
            semantic_summary="chat with Alice about plans",
            object_refs=["topic:chat", "entity:alice"],
            is_representative=True,
            representative_rank=1,
        )
        _add_atlas_item(
            session,
            atlas_run_id=atlas_run.id,
            source_item_id=102,
            region_key="region-social",
            screen_category="social",
            app_hint="telegram",
            semantic_summary="friends planning thread",
            object_refs=["topic:friends", "entity:alice"],
            is_representative=True,
            representative_rank=2,
        )
        _add_atlas_item(
            session,
            atlas_run_id=atlas_run.id,
            source_item_id=103,
            region_key="region-social",
            screen_category="chat",
            app_hint="whatsapp",
            semantic_summary="whatsapp follow-up with Bob",
            object_refs=["topic:whatsapp", "entity:bob"],
        )
        _add_atlas_item(
            session,
            atlas_run_id=atlas_run.id,
            source_item_id=201,
            region_key="region-finance",
            screen_category="finance",
            app_hint="sheets",
            is_representative=True,
            representative_rank=1,
        )
        _add_atlas_item(
            session,
            atlas_run_id=atlas_run.id,
            source_item_id=202,
            region_key="region-finance",
            screen_category="finance",
            app_hint="telegram",
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
    semantic_summary: str | None = None,
    object_refs: list[str] | None = None,
    is_representative: bool = False,
    representative_rank: int | None = None,
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
    session.flush()
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
            connector_instance_id="similarity-test",
            screen_category=screen_category,
            has_knowledge=False,
            observed_at=datetime(2026, 4, 12, 8, 0, tzinfo=UTC),
            object_refs_json=json.dumps(object_refs or []),
            is_representative=is_representative,
            representative_rank=representative_rank,
            is_bridge=False,
            bridge_type=None,
            secondary_region_key=None,
            bridge_score=0.0,
            screenshot_detail_url=f"/screenshots/{source_item_id}",
        )
    )


def _create_fake_frontend_dist(tmp_path: Path) -> Path:
    frontend_dist_dir = tmp_path / "similarity-frontend-dist"
    assets_dir = frontend_dist_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="/assets/app.css" />
  </head>
  <body>
    <div id="root">Similarity frontend</div>
    <script type="module" src="/assets/app.js"></script>
  </body>
</html>""",
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('similarity bundle loaded');", encoding="utf-8")
    (assets_dir / "app.css").write_text("body { background: #f4f0e8; }", encoding="utf-8")
    return frontend_dist_dir


class _UnusedOcrEngine:
    def extract_text(self, image_bytes: bytes, *, media_type: str) -> Any:
        raise AssertionError("unused in similarity route tests")


class _UnusedVisionEngine:
    def interpret(self, image_bytes: bytes, *, media_type: str, ocr_text: str | None = None) -> Any:
        raise AssertionError("unused in similarity route tests")
