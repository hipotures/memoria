from __future__ import annotations

import inspect
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol

from memoria.llm_utils import extract_json_object_from_text


def build_ocr_prompt(language_hint: str) -> str:
    return (
        "You are an OCR transcription engine.\n"
        "Extract all visible text from the image exactly as displayed.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Schema:\n"
        "{\n"
        '  "full_text": string,\n'
        '  "content_tags": [string]\n'
        "}\n"
        "Rules:\n"
        "- Keep original language, casing, punctuation, and numbers.\n"
        "- Keep reading order: top-to-bottom, left-to-right.\n"
        "- full_text must contain all detected text joined with newline separators.\n"
        "- content_tags must contain short topical tags for text content, e.g. ui, settings, article, invoice, listing.\n"
        "- Preserve technical tokens exactly: hostnames, domains, URLs, IPv4/IPv6, model names, dates, and numbers.\n"
        "- Do not normalize or rewrite UI labels such as DNS Secondary, IPv4, IPv6, Gateway, Status, Model.\n"
        "- Do not translate.\n"
        "- Do not summarize.\n"
        "- Do not correct spelling.\n"
        "- Do not invent missing text.\n"
        "- If a fragment is unreadable, skip only that fragment.\n"
        f"- Language hint: {language_hint}.\n"
    )


def parse_ocr_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    full_text_value = payload.get("full_text", "")
    if full_text_value is None:
        full_text_value = ""
    full_text = str(full_text_value).strip()

    if not full_text:
        lines_raw = payload.get("lines", [])
        if not isinstance(lines_raw, list):
            raise ValueError("response field 'full_text' is empty and 'lines' is not a list")
        lines = [str(item).strip() for item in lines_raw if str(item).strip()]
        full_text = "\n".join(lines)
    else:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]

    tags_raw = payload.get("content_tags", [])
    if tags_raw is None:
        tags_raw = []
    if not isinstance(tags_raw, list):
        raise ValueError("response field 'content_tags' is not a list")
    content_tags: list[str] = []
    for tag in tags_raw:
        cleaned = str(tag).strip().lower()
        if cleaned and cleaned not in content_tags:
            content_tags.append(cleaned)

    return {"lines": lines, "text": full_text, "content_tags": content_tags}


def build_paddle_init_kwargs(
    *,
    supported_params: set[str],
    lang: str,
    use_angle_cls: bool,
    use_gpu: bool,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"lang": lang}

    if "use_textline_orientation" in supported_params:
        kwargs["use_textline_orientation"] = use_angle_cls
    elif "use_angle_cls" in supported_params:
        kwargs["use_angle_cls"] = use_angle_cls

    if "use_gpu" in supported_params:
        kwargs["use_gpu"] = use_gpu
    elif "device" in supported_params:
        kwargs["device"] = "gpu" if use_gpu else "cpu"

    return kwargs


def extract_lines_from_result(result: Any) -> list[dict[str, Any]]:
    serializable = _to_serializable(result)

    if isinstance(serializable, Mapping):
        return _extract_from_mapping(serializable)

    if not isinstance(serializable, list):
        return []

    if serializable and isinstance(serializable[0], list):
        flattened = serializable[0]
    else:
        flattened = serializable

    if flattened and isinstance(flattened[0], Mapping):
        lines: list[dict[str, Any]] = []
        for item in flattened:
            lines.extend(_extract_from_mapping(item))
        return lines

    lines = []
    for entry in flattened:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        bbox = entry[0]
        text_conf = entry[1]
        if not isinstance(text_conf, (list, tuple)) or not text_conf:
            continue
        text = str(text_conf[0])
        confidence = _safe_float(text_conf[1]) if len(text_conf) > 1 else None
        lines.append(
            {
                "text": text,
                "confidence": confidence,
                "bbox": _to_serializable(bbox),
            }
        )
    return lines


@dataclass(frozen=True, slots=True)
class OcrEngineResult:
    engine_name: str
    text_content: str
    language_hint: str | None = None
    block_map_json: str = "[]"


class OcrEngine(Protocol):
    def extract_text(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str | None = None,
    ) -> OcrEngineResult: ...


class PaddleOcrEngine:
    def __init__(
        self,
        *,
        lang: str = "en",
        use_angle_cls: bool = True,
        use_gpu: bool = False,
    ) -> None:
        self._lang = lang
        self._use_angle_cls = use_angle_cls
        self._use_gpu = use_gpu
        self._ocr_instance: Any | None = None

    def extract_text(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str | None = None,
    ) -> OcrEngineResult:
        ocr = self._get_or_create_ocr()
        suffix = _suffix_from_media_type(media_type)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(image_bytes)
            temp_path = Path(handle.name)
        try:
            raw_result = _run_ocr_on_image(
                ocr,
                temp_path,
                use_angle_cls=self._use_angle_cls,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        lines = extract_lines_from_result(raw_result)
        text_content = "\n".join(
            line["text"].strip() for line in lines if str(line.get("text", "")).strip()
        )
        return OcrEngineResult(
            engine_name="paddleocr",
            text_content=text_content,
            language_hint=language_hint,
            block_map_json=json.dumps(lines, ensure_ascii=False, sort_keys=True),
        )

    def _get_or_create_ocr(self) -> Any:
        if self._ocr_instance is not None:
            return self._ocr_instance
        self._ocr_instance = _build_ocr_engine(
            lang=self._lang,
            use_angle_cls=self._use_angle_cls,
            use_gpu=self._use_gpu,
        )
        return self._ocr_instance


def _build_ocr_engine(*, lang: str, use_angle_cls: bool, use_gpu: bool) -> Any:
    # Match the working snaptag runner: avoid Paddle's hoster connectivity preflight.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "PaddleOCR is not installed. Install it first, e.g. "
            "`uv pip install paddleocr paddlepaddle-gpu==3.3.0`."
        ) from exc

    signature = inspect.signature(PaddleOCR.__init__)
    params = signature.parameters
    supported_params = {name for name in params if name not in {"self", "kwargs"}}
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in params.values()
    )

    base_kwargs = build_paddle_init_kwargs(
        supported_params=supported_params,
        lang=lang,
        use_angle_cls=use_angle_cls,
        use_gpu=use_gpu,
    )

    attempts: list[dict[str, Any]] = [base_kwargs]
    if accepts_kwargs and "device" not in base_kwargs:
        attempts.append({**base_kwargs, "device": "gpu" if use_gpu else "cpu"})
    attempts.append(
        {
            key: value
            for key, value in base_kwargs.items()
            if key not in {"use_gpu", "device"}
        }
    )
    attempts.append({"lang": lang})

    deduped_attempts: list[dict[str, Any]] = []
    for kwargs in attempts:
        if kwargs not in deduped_attempts:
            deduped_attempts.append(kwargs)

    last_error: Exception | None = None
    for kwargs in deduped_attempts:
        try:
            return PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            last_error = exc
    if last_error is None:  # pragma: no cover
        raise RuntimeError("Unexpected error creating PaddleOCR engine")
    raise RuntimeError(f"Unable to initialize PaddleOCR: {last_error}") from last_error


def _run_ocr_on_image(ocr: Any, image_path: Path, *, use_angle_cls: bool) -> Any:
    if hasattr(ocr, "predict"):
        try:
            return ocr.predict(
                str(image_path),
                use_textline_orientation=use_angle_cls,
            )
        except TypeError:
            return ocr.predict(str(image_path))
    if hasattr(ocr, "ocr"):
        return ocr.ocr(str(image_path), cls=use_angle_cls)
    raise RuntimeError("Unsupported PaddleOCR object: expected `ocr` or `predict` method")


def _extract_from_mapping(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    texts = item.get("rec_texts") or item.get("texts") or []
    scores = item.get("rec_scores") or item.get("scores") or []
    boxes = item.get("dt_polys") or item.get("boxes") or []

    lines: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        score = _safe_float(scores[index]) if index < len(scores) else None
        box = boxes[index] if index < len(boxes) else None
        lines.append(
            {
                "text": str(text),
                "confidence": score,
                "bbox": _to_serializable(box),
            }
        )
    return lines


def _to_serializable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "tolist"):
        return _to_serializable(value.tolist())
    return str(value)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _suffix_from_media_type(media_type: str) -> str:
    if media_type == "image/png":
        return ".png"
    if media_type == "image/jpeg":
        return ".jpg"
    if media_type == "image/webp":
        return ".webp"
    return ".bin"
