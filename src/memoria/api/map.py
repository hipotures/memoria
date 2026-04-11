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
from memoria.api.schemas import SemanticMapPointDetailResponse
from memoria.map.service import get_cluster_items
from memoria.map.service import get_latest_semantic_map
from memoria.map.service import get_semantic_cluster
from memoria.map.service import get_semantic_map_point


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

    @router.get("/map/semantic/{source_item_id}", response_model=SemanticMapPointDetailResponse)
    def get_semantic_map_point_endpoint(source_item_id: int) -> dict[str, object]:
        with Session(engine) as session:
            result = get_semantic_map_point(session, source_item_id=source_item_id)
        if result is None:
            raise HTTPException(status_code=404, detail="semantic map point not found")
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
      h3 { margin: 0 0 6px; font-size: 15px; }
      .panel { margin-top: 16px; padding: 14px; border: 1px solid #d8cfba; border-radius: 14px; background: white; }
      .panel + .panel { margin-top: 12px; }
      .panel p { margin: 0; }
      #cluster-list { display: grid; gap: 10px; margin-top: 16px; }
      .cluster-card, .point-card { width: 100%; text-align: left; padding: 12px; border: 1px solid #d8cfba; border-radius: 12px; background: white; cursor: pointer; }
      .cluster-card:hover { border-color: #7f6f4f; }
      .point-card:hover { border-color: #7f6f4f; }
      .muted { color: #5e6b73; font-size: 14px; }
      .point-list { display: grid; gap: 10px; margin-top: 12px; }
      .point-card strong, .point-card .muted { display: block; }
      .point-card .muted { margin-top: 4px; }
      .detail-section + .detail-section { margin-top: 14px; }
      .ref-list { padding-left: 18px; margin: 0; }
      .detail-link { color: #7a3d20; text-decoration: none; font-weight: 600; }
      .detail-link:hover { text-decoration: underline; }
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
        <section id="cluster-detail" class="panel muted">Loading map…</section>
        <section id="point-detail" class="panel muted">
          <h2>Point detail</h2>
          <p>Select a screenshot point to inspect the semantic summary, app hint, screenshot detail link, and object refs.</p>
        </section>
        <div id="cluster-list"></div>
      </aside>
    </main>
    <script>
      async function fetchJson(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Failed to fetch ${url}`);
        return response.json();
      }

      function renderPointDetail(point) {
        const detailNode = document.getElementById('point-detail');
        const objectRefs = point.object_refs.length > 0
          ? `<ul class="ref-list">${point.object_refs.map(ref => `<li><code>${ref}</code></li>`).join('')}</ul>`
          : '<p class="muted">No object refs recorded for this point.</p>';
        detailNode.className = 'panel';
        detailNode.innerHTML = `<h2>Point detail</h2>
          <div class="detail-section">
            <h3>Semantic summary</h3>
            <p>${point.semantic_summary || 'No semantic summary available.'}</p>
          </div>
          <div class="detail-section">
            <h3>App hint</h3>
            <p>${point.app_hint || 'No app hint available.'}</p>
          </div>
          <div class="detail-section">
            <h3>Screenshot detail</h3>
            <a class="detail-link" href="${point.screenshot_detail_url}">Open screenshot detail</a>
          </div>
          <div class="detail-section">
            <h3>Object refs</h3>
            ${objectRefs}
          </div>`;
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

      async function loadPoint(sourceItemId) {
        const point = await fetchJson(`/map/semantic/${sourceItemId}`);
        renderPointDetail(point);
      }

      async function loadCluster(clusterKey) {
        const [detail, items] = await Promise.all([
          fetchJson(`/map/semantic/clusters/${clusterKey}`),
          fetchJson(`/map/semantic/clusters/${clusterKey}/items`),
        ]);
        const detailNode = document.getElementById('cluster-detail');
        detailNode.className = 'panel';
        detailNode.innerHTML = `<h2>${detail.title}</h2>
          <div class="muted">${detail.item_count} items · ${detail.top_labels.join(', ')}</div>
          <div class="point-list">${items.items.map(item => `<button type="button" class="point-card" data-source-item-id="${item.source_item_id}">
            <strong>${item.filename}</strong>
            <span class="muted">${item.semantic_summary || 'No semantic summary available.'}</span>
          </button>`).join('')}</div>`;
        detailNode.querySelectorAll('.point-card').forEach((button) => {
          button.addEventListener('click', () => loadPoint(Number(button.dataset.sourceItemId)));
        });
        if (items.items.length > 0) {
          await loadPoint(items.items[0].source_item_id);
        }
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
