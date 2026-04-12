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

from memoria.api.schemas import SimilarityGraphResponse
from memoria.similarity import service as similarity_service
from memoria.similarity.service import SimilarityGraphFilters


def create_similarity_router(*, engine: Engine, frontend_dist_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/similarity", response_class=HTMLResponse)
    def get_similarity_page() -> str:
        index_path = frontend_dist_dir / "index.html"
        if index_path.exists():
            return _rewrite_frontend_asset_paths(index_path.read_text(encoding="utf-8"))
        return _similarity_fallback_html()

    @router.get("/similarity/assets/{asset_path:path}")
    def get_similarity_asset(asset_path: str):
        asset_root = (frontend_dist_dir / "assets").resolve()
        asset_file = (asset_root / asset_path).resolve()
        if asset_root not in asset_file.parents or not asset_file.is_file():
            raise HTTPException(status_code=404, detail="similarity asset not found")
        return FileResponse(asset_file)

    @router.get("/similarity/graph", response_model=SimilarityGraphResponse)
    def get_similarity_graph_endpoint(
        connector_instance_id: str | None = Query(None),
        app_hint: str | None = Query(None),
        screen_category: str | None = Query(None),
        has_knowledge: bool | None = Query(None),
        observed_from: datetime | None = Query(None),
        observed_to: datetime | None = Query(None),
        search_query: str | None = Query(None),
        min_cluster_size: int = Query(1, ge=0),
        min_edge_weight: float = Query(0.0, ge=0.0),
    ) -> dict[str, object]:
        with Session(engine) as session:
            result = similarity_service.get_similarity_graph(
                session,
                filters=_similarity_filters(
                    connector_instance_id=connector_instance_id,
                    app_hint=app_hint,
                    screen_category=screen_category,
                    has_knowledge=has_knowledge,
                    observed_from=observed_from,
                    observed_to=observed_to,
                    search_query=search_query,
                    min_cluster_size=min_cluster_size,
                    min_edge_weight=min_edge_weight,
                ),
            )
        return asdict(result)

    return router


def _similarity_filters(
    *,
    connector_instance_id: str | None,
    app_hint: str | None,
    screen_category: str | None,
    has_knowledge: bool | None,
    observed_from: datetime | None,
    observed_to: datetime | None,
    search_query: str | None,
    min_cluster_size: int,
    min_edge_weight: float,
) -> SimilarityGraphFilters:
    return SimilarityGraphFilters(
        connector_instance_id=connector_instance_id,
        app_hint=app_hint,
        screen_category=screen_category,
        has_knowledge=has_knowledge,
        observed_from=observed_from,
        observed_to=observed_to,
        search_query=search_query,
        min_cluster_size=min_cluster_size,
        min_edge_weight=min_edge_weight,
    )


def _similarity_fallback_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Memoria Cluster Similarity Graph</title>
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
      <h1>Similarity graph frontend build is not present</h1>
      <p>The similarity graph API is available and the dedicated frontend bundle can be added later. Until then, use the JSON endpoint directly:</p>
      <ul>
        <li><code>/similarity/graph</code> for graph nodes, similarity edges, legend entries, and active filters.</li>
      </ul>
      <p class="muted">Build output was not found under <code>frontend/similarity/dist</code>.</p>
    </main>
  </body>
</html>"""


def _rewrite_frontend_asset_paths(html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        attribute = match.group(1)
        quote = match.group(2)
        raw_path = match.group(3)
        normalized = raw_path.removeprefix("./").removeprefix("/")
        return f"{attribute}={quote}/similarity/{normalized}{quote}"

    return re.sub(
        r"""(src|href)=(["'])((?:/|\./)?assets/[^"']+)["']""",
        _replace,
        html,
    )
