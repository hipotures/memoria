# Memoria: Screenshots Vertical Slice Design

## Status

- Status: approved design
- Date: 2026-04-09
- Scope: first end-to-end module for Memoria
- Source module: `screenshots`
- Success mode: `assistant-first`

---

## 1. Purpose

The first implementation slice of Memoria should prove the architecture, not the scale.

The goal is to take one source type, screenshots, and carry it through the full path:

```text
screenshot -> ingest -> canonical facts -> OCR/VLM interpretation -> absorb -> knowledge -> assistant answer -> evidence drill-down -> projections
```

This slice exists to prove that Memoria can become a personal memory-and-action system rather than another OCR or search experiment.

The user should be able to ingest a set of screenshots from one real-world thread or topic, ask a natural-language question, and receive a useful answer grounded in persistent knowledge and explicit evidence.

---

## 2. Design Outcome

The first slice will implement a balanced vertical architecture:

- real screenshot ingest,
- real canonical storage,
- real OCR and image interpretation,
- real absorb into a small knowledge layer,
- real assistant answers over that knowledge,
- real evidence drill-down,
- real read projections for assistant context and user-facing summaries.

This slice will not try to implement the whole Memoria vision at once. It will deliberately avoid full multi-source integration, full ontology coverage, and advanced lifecycle automation in V1.

---

## 3. Success Criteria

V1 is successful if all of the following are true:

1. A screenshot can be ingested and persisted as canonical source data.
2. The screenshot can be processed through OCR and semantic image interpretation.
3. The result can update a minimal but durable knowledge layer.
4. The assistant can answer a user question from the knowledge layer, not only from raw search hits.
5. The assistant can show which screenshots, OCR fragments, or claims support the answer.
6. The architecture is reusable for later source modules such as email without changing the core model.

The primary acceptance question for V1 is:

> Can the system answer a question like "What is going on with this topic lately?" from screenshots, while showing why it thinks so?

---

## 4. Scope of V1

### In scope

- Screenshot connector
- Ingress and canonical envelope handling
- Blob persistence and screenshot payload storage
- OCR and screenshot interpretation
- Minimal absorb flow into knowledge objects
- Minimal knowledge claims with evidence links
- Assistant query flow
- Read projections for assistant context and summary views
- Retrieval over canonical and knowledge layers
- Basic auditability of what claim came from which source

### Out of scope

- Email, SMS, PDF, browser history, and other source connectors
- Cross-source identity merge
- Full knowledge lifecycle engine
- Full supersession and retention policies
- Vector retrieval
- Sink/action connectors beyond later phases
- Full production UI
- Large ontology of object and relation types

---

## 5. Architectural Decision

The first module will use the **Balanced Vertical Slice** approach.

This means:

- the module will not stop at searchable OCR output,
- it will not attempt the full final architecture either,
- it will implement the smallest durable knowledge core that still makes an assistant-first experience real.

The architecture for this slice is:

```text
Screenshot Connector
-> Ingress
-> Canonical Store
-> Processing & Interpretation
-> Absorb
-> Knowledge Core
-> Projection Layer
-> Assistant Query Flow
-> Evidence Drill-Down
```

---

## 6. High-Level Flow

### 6.1 Ingest

A screenshot enters the system through a source connector.

The connector is responsible only for:

- discovering the screenshot,
- reading the source artifact,
- normalizing it to a canonical envelope,
- emitting it to ingress.

The connector is not responsible for procedural knowledge extraction or assistant logic.

### 6.2 Canonical write

Ingress validates the envelope, writes the blob, stores canonical metadata, and creates the source record.

At this point the system knows:

- what the source is,
- where it came from,
- when it was created or observed,
- what artifact is attached,
- which connector emitted it,
- what the default processing mode is.

### 6.3 Processing

The core builds a processing plan from the screenshot processing profile.

V1 should always attempt:

- OCR
- screenshot semantic description
- screenshot classification

Absorb requires:

- screenshot classification baseline, and
- at least one usable grounding signal from either OCR output or screenshot semantic description

V1 may also run:

- entity extraction
- topic extraction
- task extraction
- sequence grouping

### 6.4 Absorb

The absorb step maps interpretation outputs into the first durable knowledge layer.

Absorb should:

- resolve whether the screenshot belongs to an existing thread or topic,
- create or update minimal knowledge objects,
- create or update claims,
- attach evidence links,
- refresh relevant projections.

### 6.5 Assistant query

The assistant should answer from knowledge first, and only descend to canonical evidence and raw screenshots when needed.

### 6.6 Drill-down

The user must be able to inspect why the answer exists by opening evidence:

- supporting screenshot,
- OCR fragment,
- originating claim,
- related knowledge object.

---

## 7. Layer Model

This slice uses three distinct data layers.

### 7.1 Canonical layer

This is the operational source-of-truth layer.

It stores:

- source items,
- source-specific screenshot payloads,
- blobs,
- content fragments,
- interpretations,
- pipeline execution history.

The canonical layer must remain auditable and should not contain "final understanding" of the system.

### 7.2 Knowledge layer

This is the first durable understanding layer.

It stores:

- knowledge objects,
- knowledge claims,
- knowledge evidence links.

This layer should be small in V1, but real.

### 7.3 Projection layer

This is the read-model layer.

Its job is to support:

- assistant context assembly,
- user-readable summaries,
- stable views over current knowledge state.

The preferred architectural term is **projection**.

The term **materialized view** may be used only for a concrete persisted projection artifact, for example a generated summary record or a written export. The system is not using SQL materialized views in the strict relational sense.

---

## 8. Canonical Model for Screenshots

### 8.1 Required canonical records

#### `source_items`

Minimal source record.

Expected fields:

- `id`
- `source_type = screenshot`
- `source_family = screenshot`
- `connector_instance_id`
- `external_id`
- `dedup_key`
- `mode`
- `status`
- `source_created_at`
- `source_observed_at`
- `ingested_at`
- `raw_ref`

#### `source_payloads_screenshot`

Screenshot-specific payload such as:

- original file path or upload reference,
- image dimensions,
- device or app hints if available,
- file metadata.

#### `blobs`

Binary artifact reference or persisted blob metadata.

#### `content_fragments`

Normalized extracted fragments such as:

- `ocr_text`
- `title`
- `caption`
- `scene_description`
- `app_hint`

#### `interpretations`

Structured model outputs such as:

- screen category,
- semantic summary,
- extracted entities,
- extracted topics,
- extracted tasks,
- confidence values.

#### `pipeline_runs` and `stage_results`

Execution tracking for required and optional stages.

---

## 9. Knowledge Model for V1

The first slice intentionally limits the number of knowledge object types.

### 9.1 Knowledge objects

V1 supports:

- `thread`
- `topic`
- `task`
- `person`

These are enough to prove the architecture without prematurely designing the full Memoria ontology.

### 9.2 Knowledge claims

Claims are small, durable statements about current understanding.

Examples:

- "The current thread is about a Berlin trip."
- "There is an open task to book train tickets."
- "This screenshot belongs to the same conversation cluster as two earlier screenshots."
- "Alice is likely one of the people involved in this thread."

Claims in V1 must have:

- `status`
- `confidence_score`
- `first_seen_at`
- `last_confirmed_at`

V1 statuses:

- `active`
- `uncertain`

More advanced lifecycle states such as `stale` and `superseded` are intentionally deferred.

### 9.3 Evidence links

Every claim must have at least one evidence link.

Evidence links connect claims to:

- `source_item`
- relevant `content_fragment`
- relevant `interpretation`
- optional screenshot region or note later

Without evidence links, the assistant cannot justify its answers and the design fails its primary goal.

---

## 10. Processing Model

### 10.1 Processing ownership

The connector does not decide procedural steps.

The core decides what to run based on:

- `source_family`
- artifact type
- processing profile
- mode

For V1 the effective processing profile is:

- `screenshots_heavy`

### 10.2 Stage split

#### Extraction

Extraction is mechanical signal recovery from the screenshot artifact.

Examples:

- OCR text
- image metadata
- basic layout signals
- app hints if detectable

#### Interpretation

Interpretation is semantic understanding of the screenshot through VLM/LLM reasoning.

Examples:

- this is a chat screen,
- this is a table,
- this is a booking flow,
- this contains a likely follow-up or task,
- this is likely related to topic X,
- the screenshot appears to concern person Y.

For screenshots, V1 prioritizes **UI-aware interpretation** over general image captioning.

The first question is not "what beautiful scene is shown here?" but rather:

- what kind of screen is this,
- what is happening here,
- what topic or thread does it belong to,
- what action or unresolved state is implied.

### 10.3 Required stages

The following stages are required before absorb:

- ingest and blob persist
- OCR or screenshot semantic description baseline
- screenshot classification baseline

If these fail, the screenshot does not enter absorb.

### 10.4 Optional stages

The following stages are optional in V1:

- richer entity extraction
- richer task extraction
- sequence grouping
- nicer summary generation

If optional stages fail, the screenshot may still participate in retrieval and assistant answers, but with reduced quality.

---

## 11. Absorb Rules

Absorb is the key architectural step in V1.

Its job is to transform interpretation signals into durable knowledge updates.

Absorb should be treated as a deterministic mapping layer over interpretation outputs.

### 11.1 Absorb responsibilities

- identify candidate `thread`, `topic`, `task`, and `person` objects
- create new objects if matching is not strong enough
- update existing objects when the match is strong enough
- write or refresh claims
- attach evidence links
- trigger projection refresh for touched objects

### 11.2 Matching rules in V1

V1 should be conservative.

- High-confidence thread/topic/task matches may update existing objects automatically.
- Person resolution should be minimal and cautious.
- Ambiguous identity merging should not be solved aggressively in the screenshot slice.

### 11.3 Example

If a screenshot contains a Telegram conversation about a Berlin trip:

- canonical layer stores the screenshot, OCR, and interpretation
- absorb updates or creates:
  - `thread:alice-berlin-chat`
  - `topic:trip-to-berlin`
  - `task:book-train`
  - possibly `person:alice`
- evidence links connect each claim to the actual screenshot-derived artifacts

---

## 12. Projection Layer

The projection layer exists so the assistant does not have to rediscover state from scratch on every query.

### 12.1 Projection types for V1

V1 should support:

- `assistant_context_projection`
- `thread_summary_projection`
- `topic_status_projection`
- `daily_digest_projection`

These projections may be persisted or generated on demand, but architecturally they are read-models, not truth stores.

### 12.2 Why projections exist

They exist to:

- reduce repeated synthesis work,
- stabilize assistant responses,
- present current state clearly,
- separate knowledge storage from response formatting.

### 12.3 What projections are not

They are not:

- the main storage layer,
- the search index,
- a substitute for evidence links,
- mandatory markdown files.

Markdown export is allowed later as one projection format, but it is not the primary product of V1.

---

## 13. Assistant-First Query Model

This slice is designed around the assistant as the main interface.

### 13.1 Query intent classes

V1 should support at least:

- `find`
- `summarize`
- `status`
- `recall`

### 13.2 Query flow

1. Understand the user query.
2. Identify candidate knowledge objects.
3. Read projections and active claims first.
4. Use retrieval over canonical fragments when more grounding is needed.
5. Descend to raw screenshots only when the answer needs proof or disambiguation.
6. Return an answer in natural language.
7. Show evidence on demand.

### 13.3 Example question

For a question such as:

> "What has been going on lately with the Berlin trip?"

The system should:

- locate the relevant `topic`,
- pull linked `thread` and `task` objects,
- read the topic status projection,
- inspect newest claims and evidence,
- answer with:
  - current state,
  - open tasks,
  - unresolved points,
  - evidence references.

---

## 14. Retrieval Strategy for V1

V1 retrieval should be simple and sufficient.

### 14.1 Required retrieval channels

- FTS over canonical text fragments
- retrieval over knowledge objects and claims

### 14.2 Not yet required

- vector search
- complex graph traversal across many source domains

The retrieval model for the slice is:

- knowledge first,
- canonical search second,
- raw screenshot third.

---

## 15. Error Handling

The first slice must tolerate partial failure.

### 15.1 Hard failures

Hard failure prevents absorb:

- missing blob persistence
- no usable OCR and no usable screenshot semantic interpretation
- failure to produce minimum classification baseline

### 15.2 Soft failures

Soft failure reduces quality but not baseline usefulness:

- richer entity extraction failure
- sequence grouping failure
- projection refresh failure, if the underlying knowledge write succeeded

Soft failures should be visible in pipeline status and replayable.

---

## 16. Acceptance Tests

The slice should include acceptance scenarios proving end-to-end value.

### 16.1 Required scenarios

1. Ingest one screenshot and complete the full path through absorb.
2. Ingest multiple screenshots from the same topic and update one topic/thread consistently.
3. Ask a status question and receive an answer built from knowledge, not only raw OCR.
4. Ask a recall question such as whether there is an unresolved follow-up.
5. Drill down from answer to supporting screenshots and OCR.
6. Confirm that optional-stage failure does not destroy the assistant baseline.

### 16.2 Definition of done

The slice is done when a real screenshot set can support:

- a natural-language question,
- a knowledge-based answer,
- explicit evidence grounding,
- no manual page curation.

---

## 17. Recommended Module Boundaries

The slice should roughly separate into:

- `connectors/screenshots`
- `ingress`
- `canonical`
- `processing/ocr`
- `processing/vision`
- `processing/interpretation`
- `absorb`
- `knowledge`
- `projections`
- `assistant/query`

These boundaries may map to code packages or services later, but in V1 they should at least exist as responsibility boundaries.

---

## 18. What This Slice Proves

If this design works, it proves:

- the Memoria core model can hold real source data,
- OCR and VLM/LLM interpretation can coexist as one screenshot understanding layer,
- absorb can create durable knowledge rather than temporary search artifacts,
- assistant-first usage is viable,
- evidence-grounded answers are possible,
- the architecture is suitable for horizontal expansion to additional source modules.

If this design fails, the failure will be architectural and observable early, which is exactly what a good first vertical slice should surface.

---

## 19. Open Decisions Deferred Past Design Approval

These are valid implementation questions, but they do not block the design itself:

1. Exact schema shape of `knowledge_object` versus `knowledge_claim`
2. Exact storage format for persisted projections
3. Exact confidence scoring formula in V1
4. Exact replay and retry semantics for absorb and projection refresh
5. Exact assistant API surface

These belong in the implementation plan, not in the architectural decision for the slice.

---

## 20. Final Design Statement

The first Memoria module should be a screenshot-based, assistant-first vertical slice that:

- ingests real screenshots,
- interprets them through OCR and VLM/LLM,
- absorbs them into a small but durable knowledge layer,
- maintains read projections for assistant use,
- answers user questions from that knowledge,
- and always preserves a path back to evidence.

This is the smallest slice that proves Memoria is becoming a personal memory system rather than a screenshot search tool.
