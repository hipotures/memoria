# Memoria

Current screenshot vertical slice:

- ingest screenshots into canonical storage
- persist OCR text and screenshot interpretations
- absorb screenshot meaning into knowledge objects and claims
- refresh assistant-facing projections
- answer assistant queries with evidence-backed results
- list persisted screenshots without running assistant retrieval
- fetch screenshot detail, including canonical, derived, knowledge, and pipeline state
- search screenshots directly by persisted text fragments
- stream screenshot image bytes from the API

Local verification:

```bash
uv run pytest -v
```

Read-only screenshot API:

- `GET /screenshots`
- `GET /screenshots/search?q=Berlin`
- `GET /screenshots/{source_item_id}`
- `GET /screenshots/{source_item_id}/blob`

These endpoints expose only persisted state. They do not trigger OCR, vision, absorb, or projection refresh.

Partial screenshot detail is expected:

- ingest-only screenshots return `ocr: null` and `interpretation: null`
- OCR-only screenshots return `interpretation: null`
- screenshots without knowledge return `knowledge.object_refs=[]` and `knowledge.claims=[]`
