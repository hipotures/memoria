from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import KnowledgeThreadResponse
from memoria.api.schemas import KnowledgeTopicResponse
from memoria.knowledge.read.service import get_thread_view
from memoria.knowledge.read.service import get_topic_view


def create_knowledge_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/knowledge/topics/{slug}", response_model=KnowledgeTopicResponse)
    def get_knowledge_topic(slug: str) -> dict[str, object]:
        with Session(engine) as session:
            result = get_topic_view(session, slug=slug)
        if result is None:
            raise HTTPException(status_code=404, detail="topic not found")
        return asdict(result)

    @router.get("/knowledge/threads/{slug}", response_model=KnowledgeThreadResponse)
    def get_knowledge_thread(slug: str) -> dict[str, object]:
        with Session(engine) as session:
            result = get_thread_view(session, slug=slug)
        if result is None:
            raise HTTPException(status_code=404, detail="thread not found")
        return asdict(result)

    return router
