from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlite_vec import serialize_float32

from memoria.domain.models import Embedding

EMBEDDING_DIMENSION = 96
EMBEDDING_MODEL_NAME = "hashed-text-v1"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class EmbeddingMatch:
    source_item_id: int
    distance: float


def build_embedding_text_for_screenshot(
    *,
    filename: str,
    screen_category: str,
    semantic_summary: str,
    app_hint: str | None,
    searchable_labels: list[str],
    cluster_hints: list[str],
    entity_mentions: list[str],
    ocr_text: str,
) -> str:
    parts = [
        filename.strip(),
        screen_category.strip(),
        semantic_summary.strip(),
        (app_hint or "").strip(),
        " ".join(searchable_labels),
        " ".join(cluster_hints),
        " ".join(entity_mentions),
        ocr_text.strip()[:1200],
    ]
    return "\n".join(part for part in parts if part)


def embed_text(text_value: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    tokens = _TOKEN_RE.findall(text_value.lower())
    for token in tokens:
        _apply_feature(vector, token, weight=1.0)
    for left, right in zip(tokens, tokens[1:]):
        _apply_feature(vector, f"{left}_{right}", weight=1.5)
    for token in tokens:
        if len(token) < 3:
            continue
        for index in range(len(token) - 2):
            _apply_feature(vector, f"tri:{token[index:index + 3]}", weight=0.35)

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0.0:
        vector[0] = 1.0
        return vector
    return [value / magnitude for value in vector]


def upsert_embedding(
    session: Session,
    *,
    source_item_id: int | None,
    embedding_type: str,
    model_name: str,
    content_text: str,
    vector: list[float],
    object_ref: str | None = None,
) -> int:
    embedding_row = session.scalar(
        select(Embedding).where(
            Embedding.source_item_id == source_item_id,
            Embedding.object_ref == object_ref,
            Embedding.embedding_type == embedding_type,
        )
    )
    if embedding_row is None:
        embedding_row = Embedding(
            source_item_id=source_item_id,
            object_ref=object_ref,
            embedding_type=embedding_type,
            model_name=model_name,
            content_text=content_text,
            dimension=EMBEDDING_DIMENSION,
        )
        session.add(embedding_row)
        session.flush()
    else:
        embedding_row.model_name = model_name
        embedding_row.content_text = content_text
        embedding_row.dimension = EMBEDDING_DIMENSION
        session.add(embedding_row)
        session.flush()

    session.execute(
        text("delete from embedding_vec_items where embedding_id = :embedding_id"),
        {"embedding_id": embedding_row.id},
    )
    session.execute(
        text(
            "insert into embedding_vec_items(embedding_id, embedding) "
            "values (:embedding_id, :embedding)"
        ),
        {
            "embedding_id": embedding_row.id,
            "embedding": serialize_float32(vector),
        },
    )
    session.flush()
    return embedding_row.id


def search_embedding_matches(
    session: Session,
    *,
    embedding_type: str,
    query_text: str,
    limit: int,
) -> list[EmbeddingMatch]:
    normalized_limit = max(limit, 1)
    query_vector = embed_text(query_text)
    rows = session.execute(
        text(
            """
            select e.source_item_id, v.distance
            from embedding_vec_items as v
            join embeddings as e on e.id = v.embedding_id
            where e.embedding_type = :embedding_type
              and e.source_item_id is not null
              and v.embedding match :embedding
              and k = :k
            order by v.distance asc
            """
        ),
        {
            "embedding_type": embedding_type,
            "embedding": serialize_float32(query_vector),
            "k": normalized_limit,
        },
    ).fetchall()
    return [
        EmbeddingMatch(source_item_id=int(row[0]), distance=float(row[1]))
        for row in rows
        if row[0] is not None
    ]


def _apply_feature(vector: list[float], feature: str, *, weight: float) -> None:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
    index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
    sign = -1.0 if digest[4] % 2 else 1.0
    vector[index] += sign * weight
