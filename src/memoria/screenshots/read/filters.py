from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists
from sqlalchemy import select

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import SourceItem


@dataclass(frozen=True, slots=True)
class ScreenshotReadFilters:
    connector_instance_id: str | None = None
    app_hint: str | None = None
    screen_category: str | None = None
    has_knowledge: bool | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None

    def has_any(self) -> bool:
        return any(
            value is not None
            for value in (
                self.connector_instance_id,
                self.app_hint,
                self.screen_category,
                self.has_knowledge,
                self.observed_from,
                self.observed_to,
            )
        )


def build_screenshot_filter_clauses(filters: ScreenshotReadFilters) -> list[object]:
    clauses: list[object] = []

    if filters.connector_instance_id is not None:
        clauses.append(SourceItem.connector_instance_id == filters.connector_instance_id)
    if filters.app_hint is not None:
        clauses.append(
            exists(
                select(1).where(
                    AssetInterpretation.source_item_id == SourceItem.id,
                    AssetInterpretation.app_hint == filters.app_hint,
                )
            )
        )
    if filters.screen_category is not None:
        clauses.append(
            exists(
                select(1).where(
                    AssetInterpretation.source_item_id == SourceItem.id,
                    AssetInterpretation.screen_category == filters.screen_category,
                )
            )
        )
    if filters.observed_from is not None:
        clauses.append(SourceItem.source_observed_at >= filters.observed_from)
    if filters.observed_to is not None:
        clauses.append(SourceItem.source_observed_at <= filters.observed_to)

    evidence_exists = exists(
        select(KnowledgeEvidenceLink.id).where(KnowledgeEvidenceLink.source_item_id == SourceItem.id)
    )
    if filters.has_knowledge is True:
        clauses.append(evidence_exists)
    elif filters.has_knowledge is False:
        clauses.append(~evidence_exists)

    return clauses
