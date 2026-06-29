from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


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


@dataclass(frozen=True, slots=True)
class AtlasCandidateItem:
    source_item_id: int
    vector: list[float]
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]
    knowledge_count: int

    @property
    def metadata_score(self) -> float:
        return (
            (2.0 if self.semantic_summary else 0.0)
            + (1.0 if self.app_hint else 0.0)
            + min(float(len(self.object_refs)), 2.0)
            + min(float(self.knowledge_count), 3.0)
        )

    @property
    def near_duplicate_key(self) -> tuple[str, ...]:
        parts: list[str] = []
        normalized_summary = " ".join(self.semantic_summary.lower().split()) if self.semantic_summary else ""
        if normalized_summary:
            parts.append(f"summary:{normalized_summary}")
        if self.app_hint:
            parts.append(f"app:{self.app_hint}")
        parts.extend(f"obj:{ref}" for ref in sorted(set(self.object_refs)))
        if not parts:
            return (f"source:{self.source_item_id}",)
        return tuple(parts)


@dataclass(frozen=True, slots=True)
class BridgeClassification:
    primary_region_key: str
    secondary_region_key: str
    bridge_type: str
    bridge_score: float


@dataclass(frozen=True, slots=True)
class PriorRegionIdentity:
    region_key: str
    source_item_ids: set[int]
    centroid: list[float]
    label_tokens: set[str] = field(default_factory=set)
