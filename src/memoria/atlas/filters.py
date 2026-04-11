from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AtlasFilters:
    connector_instance_id: str | None = None
    app_hint: str | None = None
    screen_category: str | None = None
    has_knowledge: bool | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    search_query: str | None = None
