from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from memoria.domain.models import SourceItem
from memoria.screenshots.read.filters import ScreenshotReadFilters
from memoria.screenshots.read.filters import build_screenshot_filter_clauses


def test_screenshot_read_filters_drop_empty_values_and_keep_explicit_bounds() -> None:
    filters = ScreenshotReadFilters(
        connector_instance_id="manual-upload",
        app_hint="telegram",
        screen_category="chat",
        has_knowledge=True,
        observed_from=datetime(2026, 4, 2, 0, 0, 0),
        observed_to=datetime(2026, 4, 4, 23, 59, 59),
    )

    assert filters.connector_instance_id == "manual-upload"
    assert filters.app_hint == "telegram"
    assert filters.screen_category == "chat"
    assert filters.has_knowledge is True
    assert filters.observed_from == datetime(2026, 4, 2, 0, 0, 0)
    assert filters.observed_to == datetime(2026, 4, 4, 23, 59, 59)
    assert filters.has_any() is True


def test_build_screenshot_filter_clauses_include_knowledge_existence_and_bounds() -> None:
    filters = ScreenshotReadFilters(
        connector_instance_id="manual-upload",
        app_hint="telegram",
        screen_category="chat",
        has_knowledge=True,
        observed_from=datetime(2026, 4, 2, 0, 0, 0),
        observed_to=datetime(2026, 4, 4, 23, 59, 59),
    )

    clauses = build_screenshot_filter_clauses(filters)
    sql = str(select(SourceItem.id).where(*clauses).compile(compile_kwargs={"literal_binds": True}))

    assert len(clauses) == 6
    assert "source_items.connector_instance_id = 'manual-upload'" in sql
    assert sql.count("EXISTS (SELECT 1") >= 2
    assert "asset_interpretations.source_item_id = source_items.id" in sql
    assert "asset_interpretations.app_hint = 'telegram'" in sql
    assert "asset_interpretations.screen_category = 'chat'" in sql
    assert "source_items.source_observed_at >= '2026-04-02 00:00:00'" in sql
    assert "source_items.source_observed_at <= '2026-04-04 23:59:59'" in sql
    assert "EXISTS" in sql
    assert "FROM asset_interpretations, source_items" not in sql


def test_build_screenshot_filter_clauses_supports_negative_knowledge_filter() -> None:
    filters = ScreenshotReadFilters(has_knowledge=False)

    clauses = build_screenshot_filter_clauses(filters)
    sql = str(select(SourceItem.id).where(*clauses).compile(compile_kwargs={"literal_binds": True}))

    assert len(clauses) == 1
    assert "NOT (EXISTS" in sql or "NOT EXISTS" in sql
