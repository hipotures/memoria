from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from memoria.domain.models import PipelineRun
from memoria.domain.models import StageResult


def start_pipeline_run(
    session: Session,
    *,
    source_item_id: int,
    pipeline_name: str,
) -> PipelineRun:
    pipeline_run = PipelineRun(
        source_item_id=source_item_id,
        pipeline_name=pipeline_name,
        status="running",
        run_reason="ingest",
    )
    session.add(pipeline_run)
    session.flush()
    return pipeline_run


def record_stage_result(
    session: Session,
    *,
    pipeline_run_id: int,
    stage_name: str,
    status: str,
    output_payload: Any = None,
    error_text: str | None = None,
    attempt: int = 1,
) -> StageResult:
    finished_at = _utc_now() if status in {"completed", "failed"} else None
    stage_result = StageResult(
        pipeline_run_id=pipeline_run_id,
        stage_name=stage_name,
        status=status,
        attempt=attempt,
        output_json=None if output_payload is None else json.dumps(output_payload, sort_keys=True),
        error_text=error_text,
        finished_at=finished_at,
    )
    session.add(stage_result)
    session.flush()
    return stage_result


def mark_pipeline_run_completed(session: Session, pipeline_run: PipelineRun) -> PipelineRun:
    pipeline_run.status = "completed"
    pipeline_run.finished_at = _utc_now()
    session.add(pipeline_run)
    session.flush()
    return pipeline_run


def mark_pipeline_run_failed(session: Session, pipeline_run: PipelineRun) -> PipelineRun:
    pipeline_run.status = "failed"
    pipeline_run.finished_at = _utc_now()
    session.add(pipeline_run)
    session.flush()
    return pipeline_run


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
