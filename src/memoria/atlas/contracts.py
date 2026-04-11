from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AtlasWorldPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class AtlasRegionShape:
    shape_type: str
    rings: list[list[AtlasWorldPoint]]


@dataclass(frozen=True, slots=True)
class AtlasRequestOverlay:
    match_count: int
    matched_source_item_ids: list[int]
