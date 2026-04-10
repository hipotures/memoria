# Memoria

Memoria is a personal memory, knowledge, retrieval, and action system.

Its purpose is not to be “just another notes app”, OCR tool, or document index. The project is meant to become a personal operating layer over a user’s digital life: screenshots, email, chats, PDFs, files, browser traces, bookmarks, photos, and other archives should flow into one coherent model that supports recall, synthesis, and action.

The system should let a user:

- find a specific artifact quickly,
- reconstruct what happened around a topic,
- ask questions across many sources,
- inspect evidence behind an answer,
- turn understanding into explicit, user-approved actions.

## Project Goal

The full project should close the loop:

```text
source -> ingest -> canonical record -> interpretation -> knowledge
       -> retrieval -> assistant answer -> proposed action -> new source/state
```

Memoria is designed as a system that preserves provenance, builds durable knowledge above raw sources, and gives the user one assistant-first interface over many fragmented applications and archives.

## What Memoria Should Be

Memoria should become:

- a unified ingestion layer for many source families,
- a canonical store that preserves original source truth,
- a processing system that extracts structure and meaning,
- a durable knowledge layer that survives individual source views,
- a projection layer for stable read models and summaries,
- an assistant layer for recall, synthesis, and evidence-backed answers,
- an action layer that can prepare outputs for explicit user approval.

Memoria should not collapse into:

- a plain markdown vault,
- a thin wrapper around semantic search,
- a one-off screenshot OCR pipeline,
- a black-box assistant with no inspectable grounding.

## Design Principles

The project is guided by a few hard constraints:

- source data is immutable,
- provenance is first-class,
- connectors may be polyglot, but the core should stay language-consistent,
- the canonical layer is not the same thing as the knowledge layer,
- knowledge must be incremental rather than rebuilt from scratch,
- identity and relations are core features, not optional enrichments,
- every answer should be traceable back to supporting evidence,
- user-facing actions should be explicit and approved, not silently executed.

## System Architecture

Memoria is intended to have seven logical layers.

### 1. Source Connectors

Connectors discover, fetch, normalize, and emit source artifacts from external systems.

Examples:

- screenshots,
- email,
- chat and SMS,
- browser history,
- bookmarks,
- PDFs and local files,
- photos and image archives,
- social exports and other digital traces.

Connectors should only move data into the core through a stable contract. They should not own knowledge-building logic.

### 2. Ingress

Ingress is the single entry point into the core.

Its role is to:

- validate envelopes,
- enforce schema versioning,
- ensure idempotency and early deduplication,
- persist blobs and canonical metadata,
- register source-level relations,
- create processing work for downstream stages.

Without central ingress, each connector would drift into its own storage and consistency model.

### 3. Canonical Store

The canonical layer is the operational source of truth.

It should store:

- source items,
- source-specific payloads,
- blobs,
- content fragments,
- interpretations,
- pipeline execution history.

This layer exists to preserve what entered the system and how it was processed. It should stay auditable and provenance-rich rather than pretending to be “final understanding”.

### 4. Processing and Enrichment Pipelines

The processing layer turns raw inputs into structured intermediate outputs.

Depending on source type, this can include:

- OCR,
- semantic image or document interpretation,
- classification,
- extraction of entities, topics, tasks, and relations,
- grouping and sequencing,
- source-specific enrichment.

This layer should be modular, replay-safe, and explicitly staged.

### 5. Identity, Relations, and Knowledge Core

The knowledge layer is the first durable understanding layer above sources.

It should contain:

- objects such as people, topics, threads, tasks, places, and organizations,
- claims about those objects,
- links from claims back to evidence,
- lifecycle state for strengthening, weakening, uncertainty, and supersession.

This is where Memoria stops being a search system and starts becoming a memory system.

### 6. Retrieval and Assistant Layer

The main user interface should be assistant-first, but not assistant-only.

This layer should support:

- direct artifact lookup,
- topic reconstruction,
- question answering over knowledge first and canonical evidence second,
- evidence drill-down,
- synthesis across multiple sources,
- stable read models for views, dashboards, and summaries.

Assistant answers should be grounded, inspectable, and able to fall back gracefully when only canonical evidence exists.

### 7. Sink and Action Connectors

The project should eventually support output channels as well as input channels.

Examples:

- task systems,
- calendars,
- email or chat replies,
- exports,
- webhooks and automation endpoints.

The intended model is not autonomous execution. Memoria should prepare actions, explain why they make sense, and wait for user approval.

## Data Model

The project is built around three distinct layers of data.

### Canonical Layer

Stores raw but normalized source truth:

- source records,
- payloads,
- blobs,
- extracted fragments,
- interpretations,
- pipeline runs and stage results.

### Knowledge Layer

Stores durable understanding:

- knowledge objects,
- knowledge claims,
- knowledge evidence links.

### Projection Layer

Stores read models built from knowledge and canonical state:

- assistant context views,
- topic summaries,
- stable retrieval projections,
- user-facing summaries and exports.

Projection is the preferred architectural term. A materialized view is only one possible persisted artifact inside that layer.

## User Experience the Project Is Aiming For

A mature Memoria should let a user do all of the following from one coherent system:

- ingest data from many fragmented sources without losing provenance,
- search directly for an artifact when they know roughly what they want,
- ask higher-level questions such as “What is going on with this topic lately?”,
- inspect the supporting screenshots, OCR fragments, messages, or claims behind an answer,
- browse stable summaries rather than re-reading raw artifacts every time,
- approve suggested next actions derived from remembered context.

The important distinction is that the user should work mostly with memory, context, and evidence, not with disconnected source silos.

## Repository Shape

The repository should evolve around the core system responsibilities:

- `src/memoria/api`: ingress, read API, assistant entry points
- `src/memoria/storage`: metadata DB and blob storage
- `src/memoria/ingest`: canonical ingest and idempotent source entry
- `src/memoria/ocr`: OCR engines and OCR stage execution
- `src/memoria/vision`: screenshot and image interpretation
- `src/memoria/knowledge`: absorb logic and durable knowledge updates
- `src/memoria/projections`: read-model refresh and summary assembly
- `src/memoria/assistant`: retrieval and answer composition
- future source modules should follow the same pattern as the system expands beyond screenshots

The repo should grow by adding new source modules and read/action surfaces without collapsing the distinction between canonical state, knowledge, and projections.

## Development Direction

The project should grow incrementally through vertical slices.

The right pattern is:

1. choose one source family or one user-facing capability,
2. carry it end-to-end through canonical, processing, knowledge, projections, and retrieval,
3. prove the architecture with real persistence and evidence,
4. generalize only after the slice is coherent.

That approach keeps Memoria from becoming either an overdesigned framework with no product value or a collection of disconnected experiments.

## Non-Goals

Memoria should not aim to become:

- a generic vector database wrapper,
- a fully autonomous agent system,
- a UI-first project with no durable model underneath,
- a connector zoo without a stable core model,
- a knowledge graph that ignores raw source auditability.

## Working Principle

The long-term success criterion is simple:

> the system should be able to answer meaningful questions about a user’s digital life, show why those answers exist, and help convert them into deliberate actions.

That is the bar the project should be built against.
