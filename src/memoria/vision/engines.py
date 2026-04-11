from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Protocol

import httpx

from memoria.llm_utils import build_ollama_options_payload
from memoria.llm_utils import build_ollama_reasoning_payload
from memoria.llm_utils import extract_json_object_from_text
from memoria.llm_utils import extract_message_content_text
from memoria.llm_utils import normalize_openai_api_base_url
from memoria.llm_utils import strip_v1_suffix

_TOPIC_CANDIDATE_LIMIT = 3
_TASK_CANDIDATE_LIMIT = 3
_PERSON_CANDIDATE_LIMIT = 3
_ENTITY_MENTION_LIMIT = 6
_SEARCHABLE_LABEL_LIMIT = 8
_CLUSTER_HINT_LIMIT = 6


def extract_app_hint_from_filename(filename: str) -> str:
    import re

    app_hint_pattern = re.compile(r"^Screenshot_(\d{8})_(\d{6})_(.+)$")
    duplicate_suffix_pattern = re.compile(r"~\d+$")
    stem = Path(filename).stem
    match = app_hint_pattern.match(stem)
    if not match:
        return ""
    hint = duplicate_suffix_pattern.sub("", match.group(3)).strip()
    return hint.strip(" _-")


def build_interpretation_prompt(language_hint: str, app_hint_from_filename: str) -> str:
    app_hint_line = (
        f'- Filename app hint: "{app_hint_from_filename}". Treat this as a weak hint, not a fact.\n'
        if app_hint_from_filename
        else "- Filename app hint: unavailable.\n"
    )
    return (
        "You are a screenshot interpretation engine.\n"
        "Analyze the screenshot. Return exactly one JSON object with no extra text.\n"
        "Return structured interpretation for retrieval, clustering, and knowledge absorb.\n"
        "Schema:\n"
        "{\n"
        '  "screen_category": string,\n'
        '  "semantic_summary": string,\n'
        '  "app_hint": string | null,\n'
        '  "topic_candidates": [{"slug": string, "title": string, "confidence": number}],\n'
        '  "task_candidates": [{"slug": string, "title": string, "confidence": number}],\n'
        '  "person_candidates": [{"slug": string, "title": string, "confidence": number}],\n'
        '  "entity_mentions": [{"type": string, "text": string, "confidence": number}],\n'
        '  "searchable_labels": [string],\n'
        '  "cluster_hints": [string],\n'
        '  "confidence": {\n'
        '    "screen_category": number,\n'
        '    "semantic_summary": number,\n'
        '    "topic_candidates": number,\n'
        '    "task_candidates": number,\n'
        '    "person_candidates": number\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- screen_category must be a short reusable label like chat, article, video, shopping, banking, maps, calendar, social, document, or generic.\n"
        "- semantic_summary should be one short sentence grounded in what is visible.\n"
        "- topic/task/person candidates are optional. Only include them if they are plausibly supported by the screenshot.\n"
        f"- At most {_TOPIC_CANDIDATE_LIMIT} topic_candidates.\n"
        f"- At most {_TASK_CANDIDATE_LIMIT} task_candidates.\n"
        f"- At most {_PERSON_CANDIDATE_LIMIT} person_candidates.\n"
        f"- At most {_ENTITY_MENTION_LIMIT} entity_mentions.\n"
        f"- At most {_SEARCHABLE_LABEL_LIMIT} searchable_labels.\n"
        f"- At most {_CLUSTER_HINT_LIMIT} cluster_hints.\n"
        "- searchable_labels should contain short lexical hooks useful for search.\n"
        "- cluster_hints should contain labels that help group semantically similar screenshots.\n"
        "- confidence values must be between 0 and 1.\n"
        "- Do not output markdown.\n"
        "- Do not invent hidden context.\n"
        f"- Language hint for visible text: {language_hint}.\n"
        f"{app_hint_line}"
    )


def parse_interpretation_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    screen_category = str(payload.get("screen_category", "") or "").strip().lower()
    if not screen_category:
        screen_category = "generic"

    semantic_summary = str(
        payload.get("semantic_summary")
        or payload.get("summary_en")
        or payload.get("summary_pl")
        or ""
    ).strip()
    if not semantic_summary:
        semantic_summary = "Generic screenshot."

    app_hint = str(payload.get("app_hint", "") or "").strip().lower() or None
    topic_candidates = _coerce_candidate_list(payload.get("topic_candidates"))[:_TOPIC_CANDIDATE_LIMIT]
    task_candidates = _coerce_candidate_list(payload.get("task_candidates"))[:_TASK_CANDIDATE_LIMIT]
    person_candidates = _coerce_candidate_list(payload.get("person_candidates"))[:_PERSON_CANDIDATE_LIMIT]
    entity_mentions = _coerce_entity_mentions(payload.get("entity_mentions"))[:_ENTITY_MENTION_LIMIT]

    legacy_labels = _coerce_legacy_category_labels(payload.get("categories"))
    searchable_labels = _coerce_string_list(payload.get("searchable_labels"))[:_SEARCHABLE_LABEL_LIMIT]
    if not searchable_labels:
        searchable_labels = legacy_labels[:_SEARCHABLE_LABEL_LIMIT]
    cluster_hints = _coerce_string_list(payload.get("cluster_hints"))[:_CLUSTER_HINT_LIMIT]
    if not cluster_hints:
        cluster_hints = (searchable_labels or legacy_labels)[:_CLUSTER_HINT_LIMIT]

    confidence = _coerce_confidence(payload.get("confidence"))

    return {
        "screen_category": screen_category,
        "semantic_summary": semantic_summary,
        "app_hint": app_hint,
        "topic_candidates": topic_candidates,
        "task_candidates": task_candidates,
        "person_candidates": person_candidates,
        "entity_mentions": entity_mentions,
        "searchable_labels": searchable_labels,
        "cluster_hints": cluster_hints,
        "confidence": confidence,
    }


@dataclass(frozen=True, slots=True)
class VisionEngineResult:
    engine_name: str
    screen_category: str
    semantic_summary: str
    app_hint: str | None = None
    topic_candidates: list[dict[str, Any]] = field(default_factory=list)
    task_candidates: list[dict[str, Any]] = field(default_factory=list)
    person_candidates: list[dict[str, Any]] = field(default_factory=list)
    entity_mentions: list[dict[str, Any]] = field(default_factory=list)
    searchable_labels: list[str] = field(default_factory=list)
    cluster_hints: list[str] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    raw_model_payload: dict[str, Any] = field(default_factory=dict)


class VisionEngine(Protocol):
    def analyze(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str,
        app_hint_from_filename: str,
        ocr_text: str,
    ) -> VisionEngineResult: ...


class OllamaVisionEngine:
    def __init__(
        self,
        *,
        api_base_url: str,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_output_tokens: int | None = 800,
        keep_alive: str = "5m",
        think: str = "false",
        seed: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_base_url = api_base_url
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._keep_alive = keep_alive
        self._think = think
        self._seed = seed
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def analyze(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str,
        app_hint_from_filename: str,
        ocr_text: str,
    ) -> VisionEngineResult:
        prompt = build_interpretation_prompt(
            language_hint=language_hint,
            app_hint_from_filename=app_hint_from_filename,
        )
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        response_payload = self._post_chat(
            image_b64=image_b64,
            prompt=prompt,
            ocr_text=ocr_text,
            max_output_tokens=self._max_output_tokens,
        )
        current_token_limit = self._max_output_tokens
        truncation_retries = 0
        while (
            _ollama_response_hit_token_limit(response_payload)
            and current_token_limit is not None
            and truncation_retries < 3
        ):
            current_token_limit = _expanded_vision_token_limit(current_token_limit)
            response_payload = self._post_chat(
                image_b64=image_b64,
                prompt=prompt,
                ocr_text=ocr_text,
                max_output_tokens=current_token_limit,
            )
            truncation_retries += 1
        message = response_payload.get("message", {})
        if not isinstance(message, Mapping):
            raise ValueError("missing 'message' in Ollama response")
        raw_content = str(message.get("content", "")).strip()
        raw_payload = extract_json_object_from_text(raw_content)
        parsed = parse_interpretation_response(raw_payload)
        return _build_vision_engine_result(
            engine_name="ollama",
            parsed=parsed,
            raw_payload=raw_payload,
            filename_app_hint=app_hint_from_filename,
        )

    def _post_chat(
        self,
        *,
        image_b64: str,
        prompt: str,
        ocr_text: str,
        max_output_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "keep_alive": self._keep_alive,
            "messages": [
                {"role": "system", "content": "You output strict JSON only."},
                {
                    "role": "user",
                    "content": prompt + _ocr_excerpt_line(ocr_text),
                    "images": [image_b64],
                },
            ],
            "format": _response_schema(),
            "options": build_ollama_options_payload(
                temperature=self._temperature,
                max_output_tokens=max_output_tokens,
                ollama_num_predict=None,
                ollama_num_ctx=None,
                seed=self._seed,
            ),
        }
        payload.update(build_ollama_reasoning_payload(self._think))

        response = self._client.post(
            strip_v1_suffix(self._api_base_url) + "/api/chat",
            json=payload,
        )
        if response.status_code >= 400:
            payload_no_schema = dict(payload)
            payload_no_schema.pop("format", None)
            response = self._client.post(
                strip_v1_suffix(self._api_base_url) + "/api/chat",
                json=payload_no_schema,
            )
        response.raise_for_status()
        return response.json()


class OpenAICompatibleVisionEngine:
    def __init__(
        self,
        *,
        engine_name: str,
        api_base_url: str,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_output_tokens: int | None = 800,
        seed: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._engine_name = engine_name
        self._api_base_url = api_base_url
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._seed = seed
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def analyze(
        self,
        *,
        image_bytes: bytes,
        media_type: str,
        language_hint: str,
        app_hint_from_filename: str,
        ocr_text: str,
    ) -> VisionEngineResult:
        prompt = build_interpretation_prompt(
            language_hint=language_hint,
            app_hint_from_filename=app_hint_from_filename,
        )
        data_url = _image_bytes_to_data_url(image_bytes=image_bytes, media_type=media_type)
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": "You output strict JSON only."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt + _ocr_excerpt_line(ocr_text)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "screenshot_interpretation",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
        }
        if self._max_output_tokens is not None:
            payload["max_tokens"] = self._max_output_tokens
        if self._seed is not None:
            payload["seed"] = self._seed

        url = normalize_openai_api_base_url(self._api_base_url) + "/v1/chat/completions"
        response = self._client.post(url, json=payload)
        if response.status_code >= 400:
            error_text = response.text.lower()
            if response.status_code == 400 and (
                "response_format" in error_text or "json_schema" in error_text
            ):
                payload_no_schema = dict(payload)
                payload_no_schema.pop("response_format", None)
                response = self._client.post(url, json=payload_no_schema)
            else:
                response.raise_for_status()
        response.raise_for_status()
        response_payload = response.json()
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("missing 'choices' in response")
        message = choices[0].get("message", {})
        if not isinstance(message, Mapping):
            raise ValueError("missing 'message' in first choice")
        raw_content = extract_message_content_text(message.get("content", ""))
        raw_payload = extract_json_object_from_text(raw_content)
        parsed = parse_interpretation_response(raw_payload)
        return _build_vision_engine_result(
            engine_name=self._engine_name,
            parsed=parsed,
            raw_payload=raw_payload,
            filename_app_hint=app_hint_from_filename,
        )


def _build_vision_engine_result(
    *,
    engine_name: str,
    parsed: dict[str, Any],
    raw_payload: dict[str, Any],
    filename_app_hint: str,
) -> VisionEngineResult:
    app_hint = parsed["app_hint"] or (filename_app_hint.lower() if filename_app_hint else None)
    searchable_labels = list(parsed["searchable_labels"])
    if app_hint and app_hint not in searchable_labels:
        searchable_labels = [app_hint, *searchable_labels]
    cluster_hints = list(parsed["cluster_hints"])
    if app_hint and app_hint not in cluster_hints:
        cluster_hints = [app_hint, *cluster_hints]

    return VisionEngineResult(
        engine_name=engine_name,
        screen_category=str(parsed["screen_category"]),
        semantic_summary=str(parsed["semantic_summary"]),
        app_hint=app_hint,
        topic_candidates=list(parsed["topic_candidates"]),
        task_candidates=list(parsed["task_candidates"]),
        person_candidates=list(parsed["person_candidates"]),
        entity_mentions=list(parsed["entity_mentions"]),
        searchable_labels=searchable_labels,
        cluster_hints=cluster_hints,
        confidence=dict(parsed["confidence"]),
        raw_model_payload=raw_payload,
    )


def _expanded_vision_token_limit(max_output_tokens: int) -> int:
    return max(max_output_tokens * 2, max_output_tokens + 800)


def _ollama_response_hit_token_limit(response_payload: Mapping[str, Any]) -> bool:
    return str(response_payload.get("done_reason", "")).strip().lower() == "length"


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "screen_category": {"type": "string"},
            "semantic_summary": {"type": "string"},
            "app_hint": {"type": ["string", "null"]},
            "topic_candidates": {
                "type": "array",
                "items": _candidate_schema(),
                "maxItems": _TOPIC_CANDIDATE_LIMIT,
            },
            "task_candidates": {
                "type": "array",
                "items": _candidate_schema(),
                "maxItems": _TASK_CANDIDATE_LIMIT,
            },
            "person_candidates": {
                "type": "array",
                "items": _candidate_schema(),
                "maxItems": _PERSON_CANDIDATE_LIMIT,
            },
            "entity_mentions": {
                "type": "array",
                "items": _entity_schema(),
                "maxItems": _ENTITY_MENTION_LIMIT,
            },
            "searchable_labels": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": _SEARCHABLE_LABEL_LIMIT,
            },
            "cluster_hints": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": _CLUSTER_HINT_LIMIT,
            },
            "confidence": {
                "type": "object",
                "properties": {
                    "screen_category": {"type": "number"},
                    "semantic_summary": {"type": "number"},
                    "topic_candidates": {"type": "number"},
                    "task_candidates": {"type": "number"},
                    "person_candidates": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
        "required": [
            "screen_category",
            "semantic_summary",
            "app_hint",
            "topic_candidates",
            "task_candidates",
            "person_candidates",
            "entity_mentions",
            "searchable_labels",
            "cluster_hints",
            "confidence",
        ],
        "additionalProperties": True,
    }


def _candidate_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["slug", "title", "confidence"],
        "additionalProperties": True,
    }


def _entity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "text": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["type", "text", "confidence"],
        "additionalProperties": True,
    }


def _coerce_candidate_list(raw_value: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_value:
        if not isinstance(item, Mapping):
            continue
        slug = str(item.get("slug", "") or "").strip().lower()
        title = str(item.get("title", "") or "").strip()
        if not slug or not title:
            continue
        identity = (slug, title)
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(
            {
                "slug": slug,
                "title": title,
                "confidence": _coerce_confidence_value(item.get("confidence"), default=0.5),
            }
        )
    return candidates


def _coerce_entity_mentions(raw_value: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        return []

    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_value:
        if not isinstance(item, Mapping):
            continue
        entity_type = str(item.get("type", "") or "").strip().lower()
        text = str(item.get("text", "") or "").strip()
        if not entity_type or not text:
            continue
        identity = (entity_type, text)
        if identity in seen:
            continue
        seen.add(identity)
        mentions.append(
            {
                "type": entity_type,
                "text": text,
                "confidence": _coerce_confidence_value(item.get("confidence"), default=0.5),
            }
        )
    return mentions


def _coerce_string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        if not isinstance(item, str):
            continue
        value = item.strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _coerce_legacy_category_labels(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    labels: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        value = ""
        if isinstance(item, str):
            value = item.strip().lower()
        elif isinstance(item, Mapping):
            value = (
                str(item.get("en", "") or "").strip().lower()
                or str(item.get("pl", "") or "").strip().lower()
            )
        if not value or value in seen:
            continue
        seen.add(value)
        labels.append(value)
    return labels


def _coerce_confidence(raw_value: Any) -> dict[str, float]:
    if not isinstance(raw_value, Mapping):
        return {}
    return {
        str(key): _coerce_confidence_value(value, default=0.5)
        for key, value in raw_value.items()
        if isinstance(key, str)
    }


def _coerce_confidence_value(raw_value: Any, *, default: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _image_bytes_to_data_url(*, image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"


def _ocr_excerpt_line(ocr_text: str) -> str:
    excerpt = ocr_text.strip()
    if not excerpt:
        return ""
    return f'\n- OCR excerpt: "{excerpt[:500]}". Treat it as supporting context, not the only source of truth.\n'
