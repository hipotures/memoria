from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class CandidateRef:
    slug: str
    title: str
    confidence: float


@dataclass(slots=True)
class VisionInterpretation:
    screen_category: str
    semantic_summary: str
    app_hint: str | None = None
    topic_candidates: list[CandidateRef] = field(default_factory=list)
    task_candidates: list[CandidateRef] = field(default_factory=list)
    person_candidates: list[CandidateRef] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
