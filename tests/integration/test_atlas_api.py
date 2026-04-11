from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.integration._screenshot_read_helpers import create_test_client
from tests.integration._screenshot_read_helpers import seed_atlas_dataset


@dataclass(frozen=True, slots=True)
class _AtlasApiFixture:
    region_key: str
    subregion_keys: tuple[str, str]
    representative_source_item_ids: tuple[int, int]
    bridge_source_item_ids: tuple[int, int]
    long_tail_source_item_ids: tuple[int, int, int, int]


def test_get_atlas_overview_returns_regions_and_filter_overlays(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-overview.db")
    fixture = _seed_atlas_api_fixture(engine, tmp_path)

    response = client.get("/atlas/overview", params={"app_hint": "telegram"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["atlas_run"]["atlas_key"] == "screenshots_atlas_v1"
    assert payload["regions"]
    assert payload["edges"]
    assert payload["active_filters"]["app_hint"] == "telegram"

    target_region = next(
        region for region in payload["regions"] if region["region_key"] == fixture.region_key
    )
    assert target_region["overlay"]["match_count"] == 2
    assert any(region["overlay"]["match_count"] == 0 for region in payload["regions"])


def test_get_atlas_region_detail_returns_subregions_and_representatives(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-region-detail.db")
    fixture = _seed_atlas_api_fixture(engine, tmp_path)

    response = client.get(f"/atlas/regions/{fixture.region_key}", params={"app_hint": "telegram"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"]["region_key"] == fixture.region_key
    assert {item["region_key"] for item in payload["subregions"]} == set(fixture.subregion_keys)
    assert payload["representatives"]
    assert {
        item["source_item_id"] for item in payload["representatives"]
    } == set(fixture.representative_source_item_ids)
    assert all(item["app_hint"] == "telegram" for item in payload["representatives"])


def test_get_atlas_evidence_slice_splits_representatives_bridges_and_long_tail(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-evidence.db")
    fixture = _seed_atlas_api_fixture(engine, tmp_path)

    response = client.get(
        "/atlas/evidence",
        params={"region_key": fixture.region_key, "limit": 2, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    representative_ids = {item["source_item_id"] for item in payload["representatives"]}
    bridge_ids = {item["source_item_id"] for item in payload["bridges"]}
    long_tail_ids = {item["source_item_id"] for item in payload["long_tail_page"]["items"]}

    assert representative_ids == set(fixture.representative_source_item_ids)
    assert bridge_ids == set(fixture.bridge_source_item_ids)
    assert long_tail_ids <= set(fixture.long_tail_source_item_ids)
    assert len(payload["long_tail_page"]["items"]) == 2
    assert payload["long_tail_page"]["total"] == len(fixture.long_tail_source_item_ids)
    assert payload["section_totals"] == {
        "representatives": len(fixture.representative_source_item_ids),
        "bridges": len(fixture.bridge_source_item_ids),
        "long_tail": len(fixture.long_tail_source_item_ids),
    }
    assert representative_ids.isdisjoint(bridge_ids)
    assert representative_ids.isdisjoint(long_tail_ids)
    assert bridge_ids.isdisjoint(long_tail_ids)


def test_get_atlas_page_returns_fallback_html_when_frontend_build_is_missing(tmp_path):
    client, engine = create_test_client(tmp_path, "atlas-page.db")
    seed_atlas_dataset(engine, tmp_path, rebuild_atlas=True)

    response = client.get("/atlas")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Semantic Atlas frontend build is not present" in response.text
    assert "/atlas/overview" in response.text


def _seed_atlas_api_fixture(engine, tmp_path) -> _AtlasApiFixture:
    seeded = seed_atlas_dataset(engine, tmp_path, rebuild_atlas=True)
    assert seeded.atlas_run_id is not None

    representative_source_item_ids = (
        seeded.travel_source_item_ids[0],
        seeded.travel_source_item_ids[1],
    )
    bridge_source_item_ids = (
        seeded.travel_source_item_ids[2],
        seeded.travel_source_item_ids[3],
    )
    long_tail_source_item_ids = (
        seeded.travel_source_item_ids[4],
        seeded.travel_source_item_ids[5],
        seeded.travel_source_item_ids[6],
        seeded.travel_source_item_ids[7],
    )

    with Session(engine) as session:
        from memoria.domain.models import AtlasItem
        from memoria.domain.models import AtlasRegion

        primary_region = session.scalar(
            select(AtlasRegion)
            .where(
                AtlasRegion.atlas_run_id == seeded.atlas_run_id,
                AtlasRegion.region_key == "region-cluster-001",
            )
        )
        finance_anchor = session.scalar(
            select(AtlasItem).where(
                AtlasItem.atlas_run_id == seeded.atlas_run_id,
                AtlasItem.source_item_id == seeded.finance_source_item_ids[0],
            )
        )
        assert primary_region is not None
        assert finance_anchor is not None

        subregion_keys = (
            f"{primary_region.region_key}/subregion-01",
            f"{primary_region.region_key}/subregion-02",
        )
        subregion_shape = {
            "shape_type": "polygon",
            "rings": [[
                {"x": -240.0, "y": -110.0},
                {"x": -40.0, "y": -110.0},
                {"x": -40.0, "y": 110.0},
                {"x": -240.0, "y": 110.0},
                {"x": -240.0, "y": -110.0},
            ]],
        }

        existing_subregions = {
            region.region_key
            for region in session.scalars(
                select(AtlasRegion).where(
                    AtlasRegion.atlas_run_id == seeded.atlas_run_id,
                    AtlasRegion.parent_region_key == primary_region.region_key,
                )
            ).all()
        }
        for index, subregion_key in enumerate(subregion_keys, start=1):
            if subregion_key in existing_subregions:
                continue
            session.add(
                AtlasRegion(
                    atlas_run_id=seeded.atlas_run_id,
                    region_key=subregion_key,
                    parent_region_key=primary_region.region_key,
                    level=1,
                    title=f"Travel lane {index}",
                    x=primary_region.x,
                    y=primary_region.y,
                    label_x=primary_region.label_x,
                    label_y=primary_region.label_y,
                    region_shape_json=json.dumps(subregion_shape, sort_keys=True),
                    item_count=4,
                    top_labels_json=json.dumps(["travel planning"], sort_keys=True),
                    top_apps_json=json.dumps(["telegram", "gmail"], sort_keys=True),
                    top_people_json=json.dumps(["person:alice"], sort_keys=True),
                    top_entities_json=json.dumps(["topic:trip-to-berlin"], sort_keys=True),
                    time_start=primary_region.time_start,
                    time_end=primary_region.time_end,
                    representatives_json=json.dumps(
                        [{"rank": 1, "source_item_id": representative_source_item_ids[index - 1]}],
                        sort_keys=True,
                    ),
                    bridge_neighbors_json=json.dumps(
                        [
                            {
                                "edge_type": "semantic_bridge",
                                "region_key": finance_anchor.region_key,
                                "weight": 2.0,
                            }
                        ],
                        sort_keys=True,
                    ),
                    cohesion_score=primary_region.cohesion_score,
                )
            )

        item_roles = {
            representative_source_item_ids[0]: {
                "subregion_key": subregion_keys[0],
                "is_representative": True,
                "representative_rank": 1,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
            representative_source_item_ids[1]: {
                "subregion_key": subregion_keys[1],
                "is_representative": True,
                "representative_rank": 2,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
            bridge_source_item_ids[0]: {
                "subregion_key": subregion_keys[0],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": True,
                "bridge_type": "external_bridge",
                "secondary_region_key": finance_anchor.region_key,
                "bridge_score": 0.81,
            },
            bridge_source_item_ids[1]: {
                "subregion_key": subregion_keys[1],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": True,
                "bridge_type": "external_bridge",
                "secondary_region_key": finance_anchor.region_key,
                "bridge_score": 0.77,
            },
            long_tail_source_item_ids[0]: {
                "subregion_key": subregion_keys[0],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
            long_tail_source_item_ids[1]: {
                "subregion_key": subregion_keys[1],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
            long_tail_source_item_ids[2]: {
                "subregion_key": subregion_keys[0],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
            long_tail_source_item_ids[3]: {
                "subregion_key": subregion_keys[1],
                "is_representative": False,
                "representative_rank": None,
                "is_bridge": False,
                "bridge_type": None,
                "secondary_region_key": None,
                "bridge_score": 0.0,
            },
        }
        for source_item_id, role in item_roles.items():
            item = session.scalar(
                select(AtlasItem).where(
                    AtlasItem.atlas_run_id == seeded.atlas_run_id,
                    AtlasItem.source_item_id == source_item_id,
                )
            )
            assert item is not None
            item.region_key = primary_region.region_key
            item.subregion_key = role["subregion_key"]
            item.is_representative = bool(role["is_representative"])
            item.representative_rank = role["representative_rank"]
            item.is_bridge = bool(role["is_bridge"])
            item.bridge_type = role["bridge_type"]
            item.secondary_region_key = role["secondary_region_key"]
            item.bridge_score = float(role["bridge_score"])

        primary_region.item_count = 8
        primary_region.top_apps_json = json.dumps(["telegram", "whatsapp", "gmail"], sort_keys=True)
        primary_region.top_people_json = json.dumps(["person:alice"], sort_keys=True)
        primary_region.top_entities_json = json.dumps(["topic:trip-to-berlin"], sort_keys=True)
        primary_region.representatives_json = json.dumps(
            [
                {"rank": 1, "source_item_id": representative_source_item_ids[0]},
                {"rank": 2, "source_item_id": representative_source_item_ids[1]},
            ],
            sort_keys=True,
        )
        primary_region.bridge_neighbors_json = json.dumps(
            [
                {
                    "edge_type": "semantic_bridge",
                    "region_key": finance_anchor.region_key,
                    "weight": 2.0,
                }
            ],
            sort_keys=True,
        )
        session.commit()

    return _AtlasApiFixture(
        region_key="region-cluster-001",
        subregion_keys=subregion_keys,
        representative_source_item_ids=representative_source_item_ids,
        bridge_source_item_ids=bridge_source_item_ids,
        long_tail_source_item_ids=long_tail_source_item_ids,
    )
