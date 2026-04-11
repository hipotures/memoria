from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class KnowledgeObjectSummary:
    object_ref: str
    object_type: str
    title: str
    status: str
    confidence_score: float


@dataclass(frozen=True, slots=True)
class KnowledgeTaskStatusSummary:
    task_ref: str
    task_title: str | None
    status_value: str
    claim_status: str


@dataclass(frozen=True, slots=True)
class KnowledgeScreenshotSummary:
    source_item_id: int
    filename: str
    semantic_summary: str | None
    app_hint: str | None
    observed_at: datetime | None
    object_refs: list[str]


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceSummary:
    claim_id: int
    source_item_id: int
    fragment_type: str
    fragment_ref: str
    support_role: str


@dataclass(frozen=True, slots=True)
class KnowledgeClaimSummary:
    claim_id: int
    claim_type: str
    subject_ref: str
    predicate: str
    object_ref_or_value: str
    status: str
    confidence_score: float
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class TopicReadModel:
    topic: KnowledgeObjectSummary
    thread_refs: list[str]
    task_statuses: list[KnowledgeTaskStatusSummary]
    people: list[KnowledgeObjectSummary]
    recent_screenshots: list[KnowledgeScreenshotSummary]
    evidence: list[KnowledgeEvidenceSummary]


@dataclass(frozen=True, slots=True)
class ThreadReadModel:
    thread: KnowledgeObjectSummary
    topic_ref: str | None
    people: list[KnowledgeObjectSummary]
    claims: list[KnowledgeClaimSummary]
    recent_screenshots: list[KnowledgeScreenshotSummary]
    evidence: list[KnowledgeEvidenceSummary]
