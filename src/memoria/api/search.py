from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter
from fastapi import Query
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import HybridSearchResponse
from memoria.search.service import hybrid_search_screenshots
from memoria.screenshots.read.filters import ScreenshotReadFilters


def create_search_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/search/hybrid", response_model=HybridSearchResponse)
    def get_hybrid_search(
        q: str = Query(...),
        limit: int = Query(20, ge=0),
        offset: int = Query(0, ge=0),
        connector_instance_id: str | None = Query(None),
        app_hint: str | None = Query(None),
        screen_category: str | None = Query(None),
        has_knowledge: bool | None = Query(None),
        observed_from: datetime | None = Query(None),
        observed_to: datetime | None = Query(None),
    ) -> dict[str, object]:
        filters = ScreenshotReadFilters(
            connector_instance_id=connector_instance_id,
            app_hint=app_hint,
            screen_category=screen_category,
            has_knowledge=has_knowledge,
            observed_from=observed_from,
            observed_to=observed_to,
        )
        with Session(engine) as session:
            result = hybrid_search_screenshots(
                session,
                query=q,
                limit=limit,
                offset=offset,
                filters=filters,
            )
        return asdict(result)

    return router
