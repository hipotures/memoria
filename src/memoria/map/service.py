from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from memoria.domain.models import AssetInterpretation
from memoria.domain.models import Embedding
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import KnowledgeObject
from memoria.domain.models import SemanticCluster
from memoria.domain.models import SemanticMapPoint
from memoria.domain.models import SemanticMapRun
from memoria.domain.models import SourceItem
from memoria.domain.models import SourcePayloadScreenshot
from memoria.search.embeddings import embed_text


@dataclass(frozen=True, slots=True)
class SemanticMapClusterSummary:
    cluster_key: str
    title: str
    x: float
    y: float
    item_count: int
    top_labels: list[str]
    dominant_apps: list[str]
    time_start: datetime | None
    time_end: datetime | None


@dataclass(frozen=True, slots=True)
class SemanticMapResult:
    map_key: str
    generated_at: datetime | None
    clusters: list[SemanticMapClusterSummary]


@dataclass(frozen=True, slots=True)
class SemanticClusterDetail:
    cluster_key: str
    title: str
    item_count: int
    top_labels: list[str]
    dominant_apps: list[str]
    time_start: datetime | None
    time_end: datetime | None


@dataclass(frozen=True, slots=True)
class SemanticClusterItem:
    source_item_id: int
    filename: str
    semantic_summary: str | None
    app_hint: str | None
    object_refs: list[str]
    x: float
    y: float


def rebuild_semantic_map(session: Session, *, source_family: str) -> None:
    if source_family != "screenshot":
        raise ValueError("only screenshot source_family is supported")

    existing_runs = session.scalars(
        select(SemanticMapRun).where(SemanticMapRun.map_key == "screenshots_semantic_v1")
    ).all()
    for run in existing_runs:
        session.delete(run)
    session.flush()

    items = _load_map_items(session)
    map_run = SemanticMapRun(
        map_key="screenshots_semantic_v1",
        source_family=source_family,
        source_count=len(items),
        config_json=json.dumps({"algorithm": "greedy-centroid-v1"}, sort_keys=True),
    )
    session.add(map_run)
    session.flush()

    clusters = _cluster_items(items)
    _persist_clusters(session, map_run_id=map_run.id, clusters=clusters)


def get_latest_semantic_map(session: Session) -> SemanticMapResult:
    map_run = session.scalar(
        select(SemanticMapRun)
        .where(SemanticMapRun.map_key == "screenshots_semantic_v1")
        .order_by(SemanticMapRun.id.desc())
    )
    if map_run is None:
        return SemanticMapResult(map_key="screenshots_semantic_v1", generated_at=None, clusters=[])

    clusters = session.scalars(
        select(SemanticCluster)
        .where(SemanticCluster.map_run_id == map_run.id)
        .order_by(SemanticCluster.id.asc())
    ).all()
    return SemanticMapResult(
        map_key=map_run.map_key,
        generated_at=map_run.created_at,
        clusters=[
            SemanticMapClusterSummary(
                cluster_key=cluster.cluster_key,
                title=cluster.title,
                x=cluster.centroid_x,
                y=cluster.centroid_y,
                item_count=int((_summary_json(cluster).get("item_count") or 0)),
                top_labels=list(_summary_json(cluster).get("top_labels") or []),
                dominant_apps=list(_summary_json(cluster).get("dominant_apps") or []),
                time_start=_parse_datetime(_summary_json(cluster).get("time_start")),
                time_end=_parse_datetime(_summary_json(cluster).get("time_end")),
            )
            for cluster in clusters
        ],
    )


def get_semantic_cluster(session: Session, *, cluster_key: str) -> SemanticClusterDetail | None:
    cluster = session.scalar(
        select(SemanticCluster)
        .where(SemanticCluster.cluster_key == cluster_key)
        .order_by(SemanticCluster.id.desc())
    )
    if cluster is None:
        return None
    summary = _summary_json(cluster)
    return SemanticClusterDetail(
        cluster_key=cluster.cluster_key,
        title=cluster.title,
        item_count=int(summary.get("item_count") or 0),
        top_labels=list(summary.get("top_labels") or []),
        dominant_apps=list(summary.get("dominant_apps") or []),
        time_start=_parse_datetime(summary.get("time_start")),
        time_end=_parse_datetime(summary.get("time_end")),
    )


def get_cluster_items(session: Session, *, cluster_key: str) -> list[SemanticClusterItem]:
    points = session.scalars(
        select(SemanticMapPoint)
        .where(SemanticMapPoint.cluster_key == cluster_key)
        .order_by(SemanticMapPoint.id.asc())
    ).all()
    items: list[SemanticClusterItem] = []
    for point in points:
        payload = session.get(SourcePayloadScreenshot, point.source_item_id)
        interpretation = session.get(AssetInterpretation, point.source_item_id)
        if payload is None:
            continue
        items.append(
            SemanticClusterItem(
                source_item_id=point.source_item_id,
                filename=payload.original_filename,
                semantic_summary=None if interpretation is None else interpretation.semantic_summary,
                app_hint=None if interpretation is None else interpretation.app_hint,
                object_refs=_load_object_refs(session, source_item_id=point.source_item_id),
                x=point.x,
                y=point.y,
            )
        )
    return items


@dataclass(slots=True)
class _MapItem:
    source_item_id: int
    filename: str
    app_hint: str | None
    semantic_summary: str
    searchable_labels: list[str]
    cluster_hints: list[str]
    observed_at: datetime | None
    vector: list[float]


@dataclass(slots=True)
class _WorkingCluster:
    key: str
    centroid: list[float]
    items: list[_MapItem]
    x: float = 0.0
    y: float = 0.0


def _load_map_items(session: Session) -> list[_MapItem]:
    rows = session.execute(
        select(Embedding, SourcePayloadScreenshot, AssetInterpretation, SourceItem)
        .join(SourceItem, SourceItem.id == Embedding.source_item_id)
        .join(SourcePayloadScreenshot, SourcePayloadScreenshot.source_item_id == Embedding.source_item_id)
        .join(AssetInterpretation, AssetInterpretation.source_item_id == Embedding.source_item_id)
        .where(
            Embedding.embedding_type == "screenshot_semantic_text",
            Embedding.source_item_id.is_not(None),
            SourceItem.source_family == "screenshot",
        )
        .order_by(SourceItem.source_observed_at.asc(), SourceItem.id.asc())
    ).all()

    items: list[_MapItem] = []
    for embedding_row, payload_row, interpretation_row, source_item in rows:
        items.append(
            _MapItem(
                source_item_id=source_item.id,
                filename=payload_row.original_filename,
                app_hint=interpretation_row.app_hint,
                semantic_summary=interpretation_row.semantic_summary,
                searchable_labels=json.loads(interpretation_row.searchable_labels_json or "[]"),
                cluster_hints=json.loads(interpretation_row.cluster_hints_json or "[]"),
                observed_at=source_item.source_observed_at or source_item.source_created_at,
                vector=embed_text(embedding_row.content_text),
            )
        )
    return items


def _cluster_items(items: list[_MapItem]) -> list[_WorkingCluster]:
    clusters: list[_WorkingCluster] = []
    threshold = 0.45

    for item in items:
        best_cluster = None
        best_score = -1.0
        for cluster in clusters:
            score = _cosine_similarity(item.vector, cluster.centroid)
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is None or best_score < threshold:
            clusters.append(
                _WorkingCluster(
                    key=f"cluster-{len(clusters) + 1:03d}",
                    centroid=list(item.vector),
                    items=[item],
                )
            )
            continue

        best_cluster.items.append(item)
        best_cluster.centroid = _normalized_average([member.vector for member in best_cluster.items])

    _assign_cluster_positions(clusters)
    return clusters


def _persist_clusters(session: Session, *, map_run_id: int, clusters: list[_WorkingCluster]) -> None:
    for cluster in clusters:
        summary = _cluster_summary(cluster)
        session.add(
            SemanticCluster(
                map_run_id=map_run_id,
                cluster_key=cluster.key,
                title=summary["title"],
                summary_json=json.dumps(summary, sort_keys=True),
                centroid_x=cluster.x,
                centroid_y=cluster.y,
            )
        )

        for index, item in enumerate(cluster.items):
            item_x, item_y = _cluster_item_position(cluster=cluster, item_index=index, item_count=len(cluster.items))
            session.add(
                SemanticMapPoint(
                    map_run_id=map_run_id,
                    source_item_id=item.source_item_id,
                    cluster_key=cluster.key,
                    x=item_x,
                    y=item_y,
                    score_json=json.dumps(
                        {
                            "similarity_to_centroid": _cosine_similarity(item.vector, cluster.centroid),
                        },
                        sort_keys=True,
                    ),
                )
            )
    session.flush()


def _assign_cluster_positions(clusters: list[_WorkingCluster]) -> None:
    if not clusters:
        return
    if len(clusters) == 1:
        clusters[0].x = 0.0
        clusters[0].y = 0.0
        return

    for index, cluster in enumerate(sorted(clusters, key=lambda item: len(item.items), reverse=True)):
        angle = (2.0 * math.pi * index) / len(clusters)
        radius = 180.0 + float(24 * (index % 3))
        cluster.x = round(math.cos(angle) * radius, 3)
        cluster.y = round(math.sin(angle) * radius, 3)


def _cluster_item_position(*, cluster: _WorkingCluster, item_index: int, item_count: int) -> tuple[float, float]:
    if item_count == 1:
        return cluster.x, cluster.y
    angle = (2.0 * math.pi * item_index) / item_count
    radius = 24.0 + float(8 * (item_index % 3))
    return (
        round(cluster.x + math.cos(angle) * radius, 3),
        round(cluster.y + math.sin(angle) * radius, 3),
    )


def _cluster_summary(cluster: _WorkingCluster) -> dict[str, object]:
    label_counts: dict[str, int] = {}
    app_counts: dict[str, int] = {}
    observed_values = [item.observed_at for item in cluster.items if item.observed_at is not None]

    for item in cluster.items:
        for label in item.cluster_hints or item.searchable_labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        if item.app_hint:
            app_counts[item.app_hint] = app_counts.get(item.app_hint, 0) + 1

    top_labels = [
        label
        for label, _count in sorted(label_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
    ]
    dominant_apps = [
        app for app, _count in sorted(app_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
    ]
    title = ", ".join(top_labels[:2])
    if not title:
        title = dominant_apps[0] if dominant_apps else cluster.items[0].filename

    return {
        "title": title,
        "item_count": len(cluster.items),
        "top_labels": top_labels,
        "dominant_apps": dominant_apps,
        "time_start": None if not observed_values else min(observed_values).isoformat(),
        "time_end": None if not observed_values else max(observed_values).isoformat(),
    }


def _summary_json(cluster: SemanticCluster) -> dict[str, object]:
    return json.loads(cluster.summary_json)


def _load_object_refs(session: Session, *, source_item_id: int) -> list[str]:
    claims = session.scalars(
        select(KnowledgeClaim)
        .distinct()
        .join(KnowledgeEvidenceLink, KnowledgeEvidenceLink.claim_id == KnowledgeClaim.id)
        .where(KnowledgeEvidenceLink.source_item_id == source_item_id)
    ).all()
    refs = {claim.subject_ref for claim in claims}
    refs.update(claim.object_ref_or_value for claim in claims if ":" in claim.object_ref_or_value)
    existing_refs = set(
        session.scalars(select(KnowledgeObject.slug).where(KnowledgeObject.slug.in_(sorted(refs)))).all()
    )
    return sorted(ref for ref in refs if ref in existing_refs or ref.startswith("thread:"))


def _normalized_average(vectors: list[list[float]]) -> list[float]:
    summed = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            summed[index] += value
    magnitude = math.sqrt(sum(value * value for value in summed))
    if magnitude == 0.0:
        return [0.0] * len(summed)
    return [value / magnitude for value in summed]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _parse_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    return datetime.fromisoformat(raw_value)
