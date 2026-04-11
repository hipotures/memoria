from __future__ import annotations

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
    assert atlas_run.source_snapshot_id == f"semantic-map-run:{seeded.semantic_map_run_id}"
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


def test_rebuild_screenshot_atlas_reuses_prior_region_keys_when_shape_is_stable(tmp_path):
    from memoria.atlas.projection import rebuild_screenshot_atlas
    from memoria.domain.models import AtlasRegion

    engine = create_test_engine(tmp_path, "atlas-rebuild-stable.db")
    seed_atlas_dataset(engine, tmp_path)

    with Session(engine) as session:
        first = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    with Session(engine) as session:
        second = rebuild_screenshot_atlas(session, force=True)
        session.commit()

    assert first["top_region_keys"] == second["top_region_keys"]

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
