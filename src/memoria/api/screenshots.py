from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Response
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import ScreenshotDetailResponse
from memoria.api.schemas import ScreenshotListResponse
from memoria.api.schemas import ScreenshotSearchResponse
from memoria.screenshots.read.service import get_screenshot_detail
from memoria.screenshots.read.service import list_screenshots
from memoria.screenshots.read.service import open_screenshot_blob
from memoria.screenshots.read.service import search_screenshots


def create_screenshot_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/screenshots/search", response_model=ScreenshotSearchResponse)
    def get_screenshot_search(
        q: str = Query(...),
        limit: int = Query(20, ge=0),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = search_screenshots(
                session,
                query=q,
                limit=limit,
                offset=offset,
            )
        return asdict(result)

    @router.get("/screenshots", response_model=ScreenshotListResponse)
    def get_screenshots(
        limit: int = Query(20, ge=0),
        offset: int = Query(0, ge=0),
        connector_instance_id: str | None = None,
        has_knowledge: bool | None = None,
        q: str | None = None,
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = list_screenshots(
                session,
                limit=limit,
                offset=offset,
                connector_instance_id=connector_instance_id,
                has_knowledge=has_knowledge,
                q=q,
            )
        return asdict(result)

    @router.get("/screenshots/{source_item_id}", response_model=ScreenshotDetailResponse)
    def get_screenshot_detail_endpoint(source_item_id: int) -> dict[str, object]:
        with Session(engine) as session:
            result = get_screenshot_detail(
                session,
                source_item_id=source_item_id,
            )

        if result is None:
            raise HTTPException(status_code=404, detail="screenshot not found")

        return asdict(result)

    @router.get("/screenshots/{source_item_id}/blob")
    def get_screenshot_blob(source_item_id: int) -> Response:
        with Session(engine) as session:
            result = open_screenshot_blob(
                session,
                source_item_id=source_item_id,
            )

        if result is None:
            raise HTTPException(status_code=404, detail="screenshot blob not found")

        return Response(content=result.content, media_type=result.media_type)

    return router
