# Memoria: Screenshots V2 Alignment And Live-Import Hardening Design

## Status

- Status: ready for review
- Date: 2026-04-11
- Scope: align the screenshots vertical slice with `docs/memoria_screenshots_vertical_prd_v2_2026-04-10.md`
- Approach: read-model first, minimal refactor
- Constraint: do not disrupt active screenshot imports on the live database

---

## 1. Purpose

The current repository already implements most of the screenshot vertical slice:

```text
ingest -> OCR -> vision -> absorb -> knowledge -> projections -> assistant/search/map
```

The remaining work is no longer about inventing the vertical slice. It is about closing the gaps between the current implementation and the `v2` product document, while adding operational rules that make the next iteration safe to deploy around live imports.

This design therefore targets two outcomes:

1. close the `v2` product and API gaps with the smallest coherent set of changes;
2. make rebuild and backfill flows safe to operate when imports may still be running.

---

## 2. Design Goals

This design is successful if all of the following are true:

1. The missing `v2` read APIs exist and are consistent with the current data model.
2. Hybrid search supports the filters described in `v2`.
3. The semantic map can drill down to a specific screenshot point and linked knowledge.
4. Topic and thread views are exposed through dedicated knowledge read endpoints.
5. Existing ingest, OCR, vision, absorb, and projection write paths remain structurally intact.
6. Rebuild and backfill operations do not run by default while screenshot pipeline runs are still active.
7. The implementation can be developed and verified from a separate git worktree and a separate development database before touching the live import environment.

---

## 3. Explicit Non-Goals

This design does not include:

- markdown-first export as a required deliverable;
- a new connector type;
- a large write-path refactor;
- a distributed lock manager;
- a graph UI beyond the current semantic map direction;
- a new truth store separate from canonical, knowledge, projections, and semantic map tables.

If additional projection tuning is needed during implementation, it must remain strictly in service of the `v2` read experience and not become a broad refactor.

---

## 4. Architectural Direction

The implementation direction is **read-model first**.

That means:

- keep the current write path architecture;
- add missing user-facing and API-facing read surfaces;
- unify filtering and drill-down behavior across search, map, and knowledge views;
- add operator safeguards around rebuild operations.

The resulting architecture is:

```text
write path
  ingest -> OCR -> vision -> absorb -> projections/map rebuild

read path
  screenshots.read -> evidence-first screenshot views
  knowledge.read   -> topic/thread semantic views
  search           -> hybrid retrieval with shared filters
  map              -> cluster exploration plus point drill-down

ops path
  admin -> rebuild/backfill/reconcile guarded against active imports
```

This keeps the implementation aligned with the current repository shape while preventing more logic from leaking into unrelated modules.

---

## 5. Module Boundaries

### 5.1 `screenshots`

`screenshots` remains the evidence-first surface.

Responsibilities:

- screenshot list and detail;
- blob access;
- screenshot-centric search hits;
- raw OCR, interpretation, claims, and stage history.

This module should remain the most complete drill-down surface for a single screenshot.

### 5.2 `knowledge`

A new read-side module is added for semantic object views.

Responsibilities:

- topic detail by slug;
- thread detail by slug;
- assembling object metadata, claims, related threads, related tasks, related people, and recent screenshot evidence.

This module reads from existing `knowledge_*` tables, `projections`, and canonical screenshot metadata. It does not introduce a new source of truth.

### 5.3 `search`

`search` remains the retrieval-first surface.

Responsibilities:

- lexical retrieval;
- semantic retrieval;
- knowledge-assisted retrieval;
- shared filter handling for screenshot-oriented queries.

### 5.4 `map`

`map` remains the semantic exploration surface.

Responsibilities:

- cluster overview;
- cluster detail;
- cluster member listing;
- new point drill-down for a specific screenshot on the semantic map.

The map read layer must lead users toward screenshot evidence and linked knowledge without trying to duplicate full screenshot detail.

### 5.5 `admin`

`admin` remains the operational entrypoint.

Responsibilities:

- import;
- reconcile;
- rebuild/backfill;
- live-import safety checks and force overrides.

---

## 6. API Design

### 6.1 Hybrid Search

`GET /search/hybrid`

Current behavior is retained, but the endpoint is extended with filters:

- `connector_instance_id`
- `app_hint`
- `screen_category`
- `has_knowledge`
- `observed_from`
- `observed_to`

The endpoint remains a lightweight hit list. It should not try to embed full screenshot detail or full knowledge object views.

Each hit should continue to expose:

- screenshot identity;
- semantic summary;
- app hint;
- object refs;
- match sources;
- ranking score;
- cluster key when available.

### 6.2 Semantic Map Cluster View

`GET /map/semantic`

This remains the cluster overview endpoint. It should continue to return:

- `cluster_key`
- title
- centroid coordinates
- item count
- top labels
- dominant apps
- time range

This endpoint is the entrypoint for semantic exploration, not screenshot detail.

### 6.3 Semantic Map Point Drill-Down

`GET /map/semantic/{source_item_id}`

This endpoint is added to close the `v2` API gap.

It returns one screenshot point on the current semantic map together with:

- `source_item_id`
- `x`
- `y`
- `cluster_key`
- `semantic_summary`
- `app_hint`
- `created_at`
- `observed_at`
- `object_refs`
- a minimal evidence summary
- a stable link target to the screenshot detail endpoint

This endpoint is intentionally narrower than `/screenshots/{source_item_id}`. It exists to let the map UI move from exploration to drill-down without loading the full screenshot detail first.

### 6.4 Knowledge Topic View

`GET /knowledge/topics/{slug}`

This endpoint exposes a topic-centric read model built from existing knowledge and projection data.

Expected payload groups:

- topic metadata;
- related threads;
- task statuses;
- related people;
- recent evidence-backed screenshots;
- lightweight evidence summary.

### 6.5 Knowledge Thread View

`GET /knowledge/threads/{slug}`

This endpoint exposes a thread-centric read model.

Expected payload groups:

- thread metadata;
- parent topic;
- related people;
- linked claims;
- recent screenshots;
- evidence list.

### 6.6 Screenshot Detail Remains Canonical Drill-Down

`GET /screenshots/{source_item_id}` remains the canonical evidence drill-down surface.

The new knowledge and map endpoints must link toward screenshot detail rather than duplicate all of its payload.

---

## 7. Read Models And Query Model

### 7.1 No New Truth Store

The existing truth layers remain unchanged:

- canonical tables;
- knowledge tables;
- projections;
- semantic map tables.

No new primary storage layer is introduced.

### 7.2 `knowledge.read` Service

A new read-side service assembles topic and thread views from:

- `knowledge_objects`
- `knowledge_claims`
- `knowledge_evidence_links`
- `projections`
- `source_items`
- screenshot payload and interpretation rows

This service is allowed to compose data, but not to mutate it.

### 7.3 Shared Filter Model

A shared query/filter model is introduced and reused by:

- `search/hybrid`
- semantic map point and cluster member retrieval
- knowledge evidence and recent screenshot sections where relevant

Minimal shared filters:

- `connector_instance_id`
- `app_hint`
- `screen_category`
- `has_knowledge`
- `observed_from`
- `observed_to`

This avoids divergent filtering semantics across read surfaces.

### 7.4 Map Point Read Path

The point drill-down endpoint must be assembled from existing data:

- `semantic_map_points`
- `semantic_map_runs`
- `asset_interpretations`
- `source_items`
- knowledge claims and object refs

No dedicated point projection table is required for the first pass.

### 7.5 Projection Extension Policy

The default implementation should avoid adding new projection types.

If implementation evidence shows that topic or thread views are too expensive or duplicate too much assembly logic, one targeted projection extension may be introduced. Such an extension must be justified by measurement or repeated query complexity, not by preference alone.

---

## 8. Operational Hardening

### 8.1 Safety Classes

Operations are divided into three classes.

#### Safe read-only

These are considered safe during active import:

- read-only API calls;
- local analysis against a separate database;
- test runs against isolated temporary databases;
- development in a separate git worktree.

#### Write-safe but serialized

These operations write derived data and must not run by default while imports are active:

- `rebuild-screenshot-derived-data`
- future `rebuild-projections`
- future selective semantic map rebuilds
- schema migrations

#### Import path

Live import remains synchronous and simple. No new lock manager is introduced.

### 8.2 Admin Guard Policy

Admin rebuild and backfill commands must detect active screenshot pipeline runs.

Default behavior:

- if relevant `pipeline_runs.status = 'running'` rows exist, rebuild-style commands stop with a clear operator-facing error;
- a `--force` flag may bypass this guard intentionally.

The default should optimize for safety, not convenience.

### 8.3 Migration Policy

Schema migrations must be treated as incompatible with an actively writing import process on the same database.

Required rollout rule:

- do not run schema migrations while the live import process is still writing to that database.

### 8.4 Worktree And Environment Isolation

Implementation and verification should happen from:

- a separate git worktree;
- a separate development database;
- isolated test databases for automated verification.

This keeps design and implementation work from interfering with the live import environment.

---

## 9. Implementation Order

The intended rollout order is:

1. add read-side API and service changes;
2. add shared filter model and hybrid search filters;
3. add map point drill-down;
4. add knowledge topic/thread endpoints;
5. add admin safety guards;
6. add any projection tuning only if justified during implementation.

This order prioritizes user-visible `v2` gaps while keeping write-path risk low.

---

## 10. Verification Strategy

Verification must be performed on isolated databases.

Required test groups:

1. unit tests for shared filters and query validation;
2. integration tests for:
   - `GET /knowledge/topics/{slug}`
   - `GET /knowledge/threads/{slug}`
   - `GET /map/semantic/{source_item_id}`
   - `GET /search/hybrid` with filters
3. admin safety tests:
   - rebuild blocked by active running screenshot pipelines;
   - rebuild succeeds after pipelines are complete;
   - force override behavior is explicit and test-covered
4. full regression run across the existing suite.

No live-import environment is used for verification.

---

## 11. Definition Of Done

This design is complete in implementation when:

1. the missing `v2` endpoints exist and are tested;
2. hybrid search supports filtering by time, app, category, connector, and knowledge presence;
3. the semantic map can drill down from a point to screenshot evidence and linked knowledge;
4. topic and thread read endpoints expose evidence-backed semantic views;
5. screenshot detail remains the deepest evidence surface;
6. rebuild and backfill operations are guarded against active imports by default;
7. all new work is verified on isolated databases and developed from a separate worktree;
8. the resulting implementation passes the full regression suite.

---

## 12. Open Implementation Notes

- The existing untracked PRD documents are treated as external design input and should not be committed as part of this work.
- The implementation plan should explicitly include creating the separate worktree before code changes begin.
- The implementation plan should keep migrations and live-import rollout as explicit operational checkpoints rather than implicit assumptions.
