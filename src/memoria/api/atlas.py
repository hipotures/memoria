from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import AtlasEvidenceSliceResponse
from memoria.api.schemas import AtlasOverviewResponse
from memoria.api.schemas import AtlasRegionDetailResponse
from memoria.atlas import service as atlas_service
from memoria.screenshots.read.filters import ScreenshotReadFilters


def create_atlas_router(*, engine: Engine, frontend_dist_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/atlas", response_class=HTMLResponse)
    def get_atlas_page() -> str:
        index_path = frontend_dist_dir / "index.html"
        if index_path.exists():
            return _rewrite_frontend_asset_paths(index_path.read_text(encoding="utf-8"))
        return _atlas_fallback_html()

    @router.get("/atlas/assets/{asset_path:path}")
    def get_atlas_asset(asset_path: str):
        asset_root = (frontend_dist_dir / "assets").resolve()
        asset_file = (asset_root / asset_path).resolve()
        if asset_root not in asset_file.parents or not asset_file.is_file():
            raise HTTPException(status_code=404, detail="atlas asset not found")
        return FileResponse(asset_file)

    @router.get("/atlas/overview", response_model=AtlasOverviewResponse)
    def get_atlas_overview_endpoint(
        connector_instance_id: str | None = Query(None),
        app_hint: str | None = Query(None),
        screen_category: str | None = Query(None),
        has_knowledge: bool | None = Query(None),
        observed_from: datetime | None = Query(None),
        observed_to: datetime | None = Query(None),
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = atlas_service.get_atlas_overview(
                session,
                filters=_atlas_filters(
                    connector_instance_id=connector_instance_id,
                    app_hint=app_hint,
                    screen_category=screen_category,
                    has_knowledge=has_knowledge,
                    observed_from=observed_from,
                    observed_to=observed_to,
                ),
            )
        return asdict(result)

    @router.get("/atlas/regions/{region_key}", response_model=AtlasRegionDetailResponse)
    def get_atlas_region_detail_endpoint(
        region_key: str,
        connector_instance_id: str | None = Query(None),
        app_hint: str | None = Query(None),
        screen_category: str | None = Query(None),
        has_knowledge: bool | None = Query(None),
        observed_from: datetime | None = Query(None),
        observed_to: datetime | None = Query(None),
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = atlas_service.get_atlas_region_detail(
                session,
                region_key=region_key,
                filters=_atlas_filters(
                    connector_instance_id=connector_instance_id,
                    app_hint=app_hint,
                    screen_category=screen_category,
                    has_knowledge=has_knowledge,
                    observed_from=observed_from,
                    observed_to=observed_to,
                ),
            )
        if result is None:
            raise HTTPException(status_code=404, detail="atlas region not found")
        return asdict(result)

    @router.get("/atlas/evidence", response_model=AtlasEvidenceSliceResponse)
    def get_atlas_evidence_slice_endpoint(
        region_key: str = Query(...),
        subregion_key: str | None = Query(None),
        sort: str = Query("observed_at_desc"),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        connector_instance_id: str | None = Query(None),
        app_hint: str | None = Query(None),
        screen_category: str | None = Query(None),
        has_knowledge: bool | None = Query(None),
        observed_from: datetime | None = Query(None),
        observed_to: datetime | None = Query(None),
    ) -> dict[str, object]:
        try:
            with Session(engine) as session:
                result = atlas_service.get_atlas_evidence_slice(
                    session,
                    region_key=region_key,
                    subregion_key=subregion_key,
                    sort=sort,
                    limit=limit,
                    offset=offset,
                    filters=_atlas_filters(
                        connector_instance_id=connector_instance_id,
                        app_hint=app_hint,
                        screen_category=screen_category,
                        has_knowledge=has_knowledge,
                        observed_from=observed_from,
                        observed_to=observed_to,
                    ),
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if result is None:
            raise HTTPException(status_code=404, detail="atlas region not found")
        return asdict(result)

    return router


def _atlas_filters(
    *,
    connector_instance_id: str | None,
    app_hint: str | None,
    screen_category: str | None,
    has_knowledge: bool | None,
    observed_from: datetime | None,
    observed_to: datetime | None,
) -> ScreenshotReadFilters:
    return ScreenshotReadFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
    )


def _atlas_fallback_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Memoria Semantic Atlas</title>
    <style>
      body { margin: 0; font-family: sans-serif; background: #f3efe4; color: #17202a; }
      main { max-width: 820px; margin: 48px auto; padding: 32px; background: rgba(255, 255, 255, 0.88); border: 1px solid #d6cbb6; border-radius: 20px; }
      h1 { margin-top: 0; }
      p { line-height: 1.5; }
      code { background: #f8f4ea; padding: 2px 6px; border-radius: 6px; }
      ul { padding-left: 18px; }
      li + li { margin-top: 8px; }
      .muted { color: #5e6b73; }
    </style>
  </head>
  <body>
    <main>
      <h1>Semantic Atlas frontend build is not present</h1>
      <p>The atlas read APIs are available and the React workspace can be added later. Until then, use the JSON endpoints directly:</p>
      <ul>
        <li><code>/atlas/overview</code> for atlas run metadata, regions, edges, and request-scoped overlays.</li>
        <li><code>/atlas/regions/{region_key}</code> for subregions and representative screenshots.</li>
        <li><code>/atlas/evidence?region_key=...</code> for representatives, bridges, and long-tail evidence paging.</li>
      </ul>
      <p class="muted">Build output was not found under <code>frontend/atlas/dist</code>.</p>
    </main>
  </body>
</html>"""


def _rewrite_frontend_asset_paths(html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        attribute = match.group(1)
        quote = match.group(2)
        raw_path = match.group(3)
        normalized = raw_path.removeprefix("./").removeprefix("/")
        return f"{attribute}={quote}/atlas/{normalized}{quote}"

    return re.sub(
        r"""(src|href)=(["'])((?:/|\./)?assets/[^"']+)["']""",
        _replace,
        html,
    )
