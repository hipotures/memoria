from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi import Query
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import HybridSearchResponse
from memoria.search.service import hybrid_search_screenshots


def create_search_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/search/hybrid", response_model=HybridSearchResponse)
    def get_hybrid_search(
        q: str = Query(...),
        limit: int = Query(20, ge=0),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = hybrid_search_screenshots(
                session,
                query=q,
                limit=limit,
                offset=offset,
            )
        return asdict(result)

    return router
