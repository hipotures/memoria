from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from memoria.domain.models import ContentFragment
from memoria.domain.models import KnowledgeClaim
from memoria.domain.models import KnowledgeEvidenceLink
from memoria.domain.models import Projection

_QUESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "at",
    "for",
    "going",
    "is",
    "lately",
    "of",
    "on",
    "the",
    "to",
    "what",
    "who",
    "with",
}
_LOW_SIGNAL_QUESTION_TOKENS = {
    "involved",
    "status",
    "up",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_item_id: int
    fragment_type: str
    fragment_ref: str
    support_role: str
    claim_id: int | None = None


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    answer_text: str
    answer_source: str
    object_refs: list[str]
    evidence: list[EvidenceRef]


@dataclass(frozen=True, slots=True)
class _ProjectionMatch:
    assistant_payload: dict[str, object]
    topic_payload: dict[str, object] | None
    evidence: list[EvidenceRef]
    score: int


@dataclass(frozen=True, slots=True)
class _CanonicalFragmentMatch:
    source_item_id: int
    fragment_type: str
    fragment_ref: str
    fragment_text: str


def answer_question(session: Session, question: str) -> AssistantAnswer:
    keywords = _keywords(question)
    if not keywords:
        return _no_match_answer()

    projection_match = _select_projection_match(session, keywords=keywords)
    if projection_match is not None:
        object_refs = _projection_object_refs(
            assistant_payload=projection_match.assistant_payload,
            topic_payload=projection_match.topic_payload,
        )
        answer_text = _render_projection_answer(
            assistant_payload=projection_match.assistant_payload,
            topic_payload=projection_match.topic_payload,
        )
        return AssistantAnswer(
            answer_text=answer_text,
            answer_source="knowledge",
            object_refs=object_refs,
            evidence=projection_match.evidence,
        )

    return _answer_from_canonical_search(session, keywords=keywords)


def _no_match_answer() -> AssistantAnswer:
    return AssistantAnswer(
        answer_text="I do not have matching knowledge for that question yet.",
        answer_source="no_match",
        object_refs=[],
        evidence=[],
    )


def _select_projection_match(
    session: Session,
    *,
    keywords: list[str],
) -> _ProjectionMatch | None:
    projections = session.scalars(
        select(Projection)
        .where(Projection.projection_type == "assistant_context_projection")
        .order_by(Projection.updated_at.desc(), Projection.id.asc())
    ).all()
    if not projections:
        return None

    topic_status_payloads = {
        projection.object_ref: json.loads(projection.content_json)
        for projection in session.scalars(
            select(Projection).where(Projection.projection_type == "topic_status_projection")
        ).all()
    }

    best_match: _ProjectionMatch | None = None
    for projection in projections:
        assistant_payload = json.loads(projection.content_json)
        topic_payload = topic_status_payloads.get(projection.object_ref)
        evidence = _load_projection_evidence(session, assistant_payload=assistant_payload)
        score = _projection_score(
            assistant_payload=assistant_payload,
            topic_payload=topic_payload,
            evidence=evidence,
            keywords=keywords,
        )
        if score <= 0:
            continue

        if best_match is None or score > best_match.score:
            best_match = _ProjectionMatch(
                assistant_payload=assistant_payload,
                topic_payload=topic_payload,
                evidence=evidence,
                score=score,
            )

    return best_match


def _projection_score(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
    evidence: list[EvidenceRef],
    keywords: list[str],
) -> int:
    if not keywords:
        return 0

    search_blob = " ".join(_projection_search_terms(assistant_payload=assistant_payload))
    search_tokens = set(_tokenize(search_blob))
    overlap = sum(1 for keyword in keywords if keyword in search_tokens)
    if overlap == 0:
        return 0

    if not _projection_is_answerable(
        assistant_payload=assistant_payload,
        topic_payload=topic_payload,
        evidence=evidence,
    ):
        return 0

    topic = assistant_payload.get("topic") or {}
    topic_type = str(topic.get("object_type") or "")
    score = overlap
    if topic_type == "topic":
        score += 50
    if topic_payload is not None:
        score += 15

    title_tokens = set(_tokenize(str(topic.get("title") or "")))
    object_ref_tokens = set(_tokenize(str(topic.get("object_ref") or "")))
    score += sum(2 for keyword in keywords if keyword in title_tokens)
    score += sum(1 for keyword in keywords if keyword in object_ref_tokens)
    score += min(len(assistant_payload.get("claims", [])), 5) * 4
    score += min(len(assistant_payload.get("tasks", [])), 3) * 5
    score += min(len(assistant_payload.get("people", [])), 3) * 3
    score += min(len(assistant_payload.get("threads", [])), 3) * 2
    score += min(len(evidence), 5) * 6
    return score


def _projection_search_terms(*, assistant_payload: dict[str, object]) -> list[str]:
    topic = assistant_payload.get("topic") or {}
    terms = [
        str(topic.get("title") or ""),
        str(topic.get("object_ref") or ""),
    ]
    for thread in assistant_payload.get("threads", []):
        if not isinstance(thread, dict):
            continue
        terms.append(str(thread.get("title") or ""))
        terms.append(str(thread.get("object_ref") or ""))
    for task_entry in assistant_payload.get("tasks", []):
        if not isinstance(task_entry, dict):
            continue
        task = task_entry.get("task") or {}
        status_claim = task_entry.get("status_claim") or {}
        if isinstance(task, dict):
            terms.append(str(task.get("title") or ""))
            terms.append(str(task.get("object_ref") or ""))
        if isinstance(status_claim, dict):
            terms.append(str(status_claim.get("object_ref_or_value") or ""))
    for person_entry in assistant_payload.get("people", []):
        if not isinstance(person_entry, dict):
            continue
        person = person_entry.get("person") or {}
        if isinstance(person, dict):
            terms.append(str(person.get("title") or ""))
            terms.append(str(person.get("object_ref") or ""))
    return terms


def _projection_is_answerable(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
    evidence: list[EvidenceRef],
) -> bool:
    if not evidence:
        return False
    return _projection_has_meaningful_payload(
        assistant_payload=assistant_payload,
        topic_payload=topic_payload,
    )


def _projection_has_meaningful_payload(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
) -> bool:
    if assistant_payload.get("claims"):
        return True
    if assistant_payload.get("tasks"):
        return True
    if assistant_payload.get("people"):
        return True
    if assistant_payload.get("threads"):
        return True
    if topic_payload and (
        topic_payload.get("task_statuses")
        or topic_payload.get("people")
        or topic_payload.get("thread_refs")
    ):
        return True

    topic = assistant_payload.get("topic") or {}
    return str(topic.get("object_type") or "") == "topic"


def _render_projection_answer(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
) -> str:
    topic = assistant_payload.get("topic") or {}
    topic_title = str(topic.get("title") or "this topic")

    task_bits = _projection_task_bits(assistant_payload=assistant_payload, topic_payload=topic_payload)
    people_bits = _projection_people_bits(assistant_payload=assistant_payload, topic_payload=topic_payload)
    thread_titles = [
        str(thread.get("title"))
        for thread in assistant_payload.get("threads", [])
        if isinstance(thread, dict) and thread.get("title")
    ]

    sentences = [f"{topic_title} is active in the knowledge graph."]
    if task_bits:
        sentences.append(f"Current task status: {', '.join(task_bits)}.")
    if people_bits:
        sentences.append(f"People involved: {', '.join(people_bits)}.")
    if thread_titles:
        sentences.append(f"Recent context is linked through {', '.join(thread_titles)}.")
    return " ".join(sentences)


def _projection_task_bits(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
) -> list[str]:
    task_bits: list[str] = []
    seen: set[str] = set()

    if topic_payload is not None:
        for task_status in topic_payload.get("task_statuses", []):
            if not isinstance(task_status, dict):
                continue
            title = str(task_status.get("task_title") or task_status.get("task_ref") or "task")
            status_value = str(task_status.get("status_value") or "unknown")
            bit = f"{title} is {status_value}"
            if bit not in seen:
                task_bits.append(bit)
                seen.add(bit)

    for task_entry in assistant_payload.get("tasks", []):
        if not isinstance(task_entry, dict):
            continue
        task = task_entry.get("task") or {}
        status_claim = task_entry.get("status_claim") or {}
        if not isinstance(task, dict) or not isinstance(status_claim, dict):
            continue
        title = str(task.get("title") or task.get("object_ref") or "task")
        status_value = str(status_claim.get("object_ref_or_value") or "unknown")
        bit = f"{title} is {status_value}"
        if bit not in seen:
            task_bits.append(bit)
            seen.add(bit)

    return task_bits


def _projection_people_bits(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
) -> list[str]:
    people_bits: list[str] = []
    seen: set[str] = set()

    if topic_payload is not None:
        for person in topic_payload.get("people", []):
            if not isinstance(person, dict):
                continue
            title = str(person.get("person_title") or person.get("person_ref") or "")
            if title and title not in seen:
                people_bits.append(title)
                seen.add(title)

    for person_entry in assistant_payload.get("people", []):
        if not isinstance(person_entry, dict):
            continue
        person = person_entry.get("person") or {}
        if not isinstance(person, dict):
            continue
        title = str(person.get("title") or person.get("object_ref") or "")
        if title and title not in seen:
            people_bits.append(title)
            seen.add(title)

    return people_bits


def _projection_object_refs(
    *,
    assistant_payload: dict[str, object],
    topic_payload: dict[str, object] | None,
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    topic = assistant_payload.get("topic") or {}
    topic_ref = str(topic.get("object_ref") or "")
    if topic_ref:
        refs.append(topic_ref)
        seen.add(topic_ref)

    for thread in assistant_payload.get("threads", []):
        if not isinstance(thread, dict):
            continue
        thread_ref = str(thread.get("object_ref") or "")
        if thread_ref and thread_ref not in seen:
            refs.append(thread_ref)
            seen.add(thread_ref)

    for task_entry in assistant_payload.get("tasks", []):
        if not isinstance(task_entry, dict):
            continue
        task = task_entry.get("task") or {}
        if not isinstance(task, dict):
            continue
        task_ref = str(task.get("object_ref") or "")
        if task_ref and task_ref not in seen:
            refs.append(task_ref)
            seen.add(task_ref)

    if topic_payload is not None:
        for person in topic_payload.get("people", []):
            if not isinstance(person, dict):
                continue
            person_ref = str(person.get("person_ref") or "")
            if person_ref and person_ref not in seen:
                refs.append(person_ref)
                seen.add(person_ref)

    return refs


def _load_projection_evidence(
    session: Session,
    *,
    assistant_payload: dict[str, object],
) -> list[EvidenceRef]:
    claim_ids: list[int] = []
    for claim_payload in assistant_payload.get("claims", []):
        if not isinstance(claim_payload, dict):
            continue
        claim = session.scalar(
            select(KnowledgeClaim).where(
                KnowledgeClaim.claim_type == str(claim_payload.get("claim_type") or ""),
                KnowledgeClaim.subject_ref == str(claim_payload.get("subject_ref") or ""),
                KnowledgeClaim.predicate == str(claim_payload.get("predicate") or ""),
                KnowledgeClaim.object_ref_or_value
                == str(claim_payload.get("object_ref_or_value") or ""),
            )
        )
        if claim is not None and claim.id not in claim_ids:
            claim_ids.append(claim.id)

    if not claim_ids:
        return []

    evidence_links = session.scalars(
        select(KnowledgeEvidenceLink)
        .where(KnowledgeEvidenceLink.claim_id.in_(claim_ids))
        .order_by(KnowledgeEvidenceLink.id.asc())
    ).all()
    return [
        EvidenceRef(
            source_item_id=link.source_item_id,
            fragment_type=link.fragment_type,
            fragment_ref=link.fragment_ref,
            support_role=link.support_role,
            claim_id=link.claim_id,
        )
        for link in evidence_links
    ]


def _answer_from_canonical_search(
    session: Session,
    *,
    keywords: list[str],
) -> AssistantAnswer:
    matches = _search_canonical_fragments(session, keywords=keywords)
    if not matches:
        return _no_match_answer()

    answer_text = matches[0].fragment_text.strip()
    return AssistantAnswer(
        answer_text=answer_text,
        answer_source="canonical",
        object_refs=[],
        evidence=[
            EvidenceRef(
                source_item_id=match.source_item_id,
                fragment_type=match.fragment_type,
                fragment_ref=match.fragment_ref,
                support_role="canonical",
            )
            for match in matches
        ],
    )


def _search_canonical_fragments(
    session: Session,
    *,
    keywords: list[str],
) -> list[_CanonicalFragmentMatch]:
    if not keywords:
        return []

    if keywords:
        fts_matches = _search_canonical_fragments_via_fts(session, keywords=keywords)
        if fts_matches:
            return fts_matches

    return _search_canonical_fragments_via_like(session, keywords=keywords)


def _search_canonical_fragments_via_fts(
    session: Session,
    *,
    keywords: list[str],
) -> list[_CanonicalFragmentMatch]:
    query = _fts_query(keywords)
    if not query:
        return []

    rows = session.execute(
        text(
            """
            SELECT
                cf.source_item_id,
                cf.fragment_type,
                cf.fragment_ref,
                cf.fragment_text
            FROM content_fragments_fts
            JOIN content_fragments AS cf ON cf.id = content_fragments_fts.rowid
            WHERE content_fragments_fts MATCH :match_query
            ORDER BY bm25(content_fragments_fts), cf.id ASC
            LIMIT 5
            """
        ),
        {"match_query": query},
    ).mappings().all()

    return [
        _CanonicalFragmentMatch(
            source_item_id=int(row["source_item_id"]),
            fragment_type=str(row["fragment_type"]),
            fragment_ref=str(row["fragment_ref"]),
            fragment_text=str(row["fragment_text"]),
        )
        for row in rows
    ]


def _search_canonical_fragments_via_like(
    session: Session,
    *,
    keywords: list[str],
) -> list[_CanonicalFragmentMatch]:
    query = select(ContentFragment).order_by(ContentFragment.id.asc())
    if keywords:
        query = query.where(
            or_(*[ContentFragment.fragment_text.ilike(f"%{keyword}%") for keyword in keywords])
        )
    query = query.limit(5)

    return [
        _CanonicalFragmentMatch(
            source_item_id=fragment.source_item_id,
            fragment_type=fragment.fragment_type,
            fragment_ref=fragment.fragment_ref,
            fragment_text=fragment.fragment_text,
        )
        for fragment in session.scalars(query).all()
    ]


def _fts_query(keywords: list[str]) -> str:
    tokens = [token for token in keywords if token]
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def _keywords(question: str) -> list[str]:
    return [
        token
        for token in _tokenize(question)
        if _is_searchable_token(token)
        and token not in _QUESTION_STOPWORDS
        and token not in _LOW_SIGNAL_QUESTION_TOKENS
    ]


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.lower())


def _is_searchable_token(token: str) -> bool:
    return len(token) > 1 or token.isdigit()
