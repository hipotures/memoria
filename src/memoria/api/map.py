from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from memoria.api.schemas import SemanticClusterDetailResponse
from memoria.api.schemas import SemanticClusterItemsResponse
from memoria.api.schemas import SemanticMapResponse
from memoria.map.service import get_cluster_items
from memoria.map.service import get_latest_semantic_map
from memoria.map.service import get_semantic_cluster


def create_map_router(*, engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/map", response_class=HTMLResponse)
    def get_map_page() -> str:
        return _map_page_html()

    @router.get("/map/semantic", response_model=SemanticMapResponse)
    def get_semantic_map() -> dict[str, object]:
        with Session(engine) as session:
            result = get_latest_semantic_map(session)
        return asdict(result)

    @router.get("/map/semantic/clusters/{cluster_key}", response_model=SemanticClusterDetailResponse)
    def get_semantic_cluster_endpoint(cluster_key: str) -> dict[str, object]:
        with Session(engine) as session:
            result = get_semantic_cluster(session, cluster_key=cluster_key)
        if result is None:
            raise HTTPException(status_code=404, detail="cluster not found")
        return asdict(result)

    @router.get(
        "/map/semantic/clusters/{cluster_key}/items",
        response_model=SemanticClusterItemsResponse,
    )
    def get_semantic_cluster_items_endpoint(cluster_key: str) -> dict[str, object]:
        with Session(engine) as session:
            items = get_cluster_items(session, cluster_key=cluster_key)
        return {
            "cluster_key": cluster_key,
            "items": [asdict(item) for item in items],
        }

    return router


def _map_page_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Memoria Semantic Map</title>
    <style>
      body { font-family: sans-serif; margin: 0; background: #f7f4ea; color: #17202a; }
      main { display: grid; grid-template-columns: 1.4fr 0.9fr; min-height: 100vh; }
      #canvas { background: radial-gradient(circle at top, #fff8dc 0%, #f7f4ea 60%, #eee7d5 100%); }
      aside { padding: 24px; border-left: 1px solid #d8cfba; background: #fbf8f0; }
      h1, h2 { margin: 0 0 12px; }
      #cluster-list { display: grid; gap: 10px; margin-top: 16px; }
      .cluster-card { padding: 12px; border: 1px solid #d8cfba; border-radius: 12px; background: white; cursor: pointer; }
      .cluster-card:hover { border-color: #7f6f4f; }
      .muted { color: #5e6b73; font-size: 14px; }
      ul { padding-left: 18px; }
      .bubble { fill: #d87c4a; opacity: 0.78; stroke: #7a3d20; stroke-width: 2; cursor: pointer; }
      .bubble:hover { opacity: 0.95; }
      .bubble-label { font-size: 12px; text-anchor: middle; pointer-events: none; }
    </style>
  </head>
  <body>
    <main>
      <svg id="canvas" viewBox="-320 -260 640 520"></svg>
      <aside>
        <h1>Semantic Map</h1>
        <p class="muted">Cluster-first view over screenshot similarity. Select a cluster to inspect its members.</p>
        <div id="cluster-detail" class="muted">Loading map…</div>
        <div id="cluster-list"></div>
      </aside>
    </main>
    <script>
      async function fetchJson(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Failed to fetch ${url}`);
        return response.json();
      }

      function renderMap(payload) {
        const svg = document.getElementById('canvas');
        svg.innerHTML = '';
        for (const cluster of payload.clusters) {
          const radius = 20 + Math.min(cluster.item_count, 12) * 4;
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', cluster.x);
          circle.setAttribute('cy', cluster.y);
          circle.setAttribute('r', radius);
          circle.setAttribute('class', 'bubble');
          circle.addEventListener('click', () => loadCluster(cluster.cluster_key));
          const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          label.setAttribute('x', cluster.x);
          label.setAttribute('y', cluster.y + 4);
          label.setAttribute('class', 'bubble-label');
          label.textContent = cluster.title;
          group.appendChild(circle);
          group.appendChild(label);
          svg.appendChild(group);
        }
      }

      function renderClusterCards(payload) {
        const container = document.getElementById('cluster-list');
        container.innerHTML = '';
        for (const cluster of payload.clusters) {
          const card = document.createElement('button');
          card.type = 'button';
          card.className = 'cluster-card';
          card.innerHTML = `<strong>${cluster.title}</strong><div class="muted">${cluster.item_count} items · ${cluster.top_labels.join(', ')}</div>`;
          card.addEventListener('click', () => loadCluster(cluster.cluster_key));
          container.appendChild(card);
        }
      }

      async function loadCluster(clusterKey) {
        const [detail, items] = await Promise.all([
          fetchJson(`/map/semantic/clusters/${clusterKey}`),
          fetchJson(`/map/semantic/clusters/${clusterKey}/items`),
        ]);
        const detailNode = document.getElementById('cluster-detail');
        detailNode.innerHTML = `<h2>${detail.title}</h2>
          <div class="muted">${detail.item_count} items · ${detail.top_labels.join(', ')}</div>
          <ul>${items.items.map(item => `<li><strong>${item.filename}</strong><br /><span class="muted">${item.semantic_summary || ''}</span></li>`).join('')}</ul>`;
      }

      (async () => {
        const payload = await fetchJson('/map/semantic');
        renderMap(payload);
        renderClusterCards(payload);
        if (payload.clusters.length > 0) {
          await loadCluster(payload.clusters[0].cluster_key);
        } else {
          document.getElementById('cluster-detail').textContent = 'No semantic clusters available yet.';
        }
      })();
    </script>
  </body>
</html>"""
