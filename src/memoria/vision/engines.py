from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
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


def build_category_prompt(language_hint: str, app_hint_from_filename: str) -> str:
    app_hint_line = (
        f'- Filename app hint: "{app_hint_from_filename}". Treat this as a weak hint, not a fact.\n'
        if app_hint_from_filename
        else "- Filename app hint: unavailable.\n"
    )
    return (
        "You are a screenshot categorization engine.\n"
        "Analyze the image and return exactly one JSON object with no extra text.\n"
        "Schema:\n"
        "{\n"
        '  "summary_pl": string,\n'
        '  "summary_en": string,\n'
        '  "categories": [\n'
        "    {\n"
        '      "pl": string,\n'
        '      "en": string\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- categories must contain 5 to 7 unique category pairs.\n"
        "- Each category must be short and reusable (usually 1-3 words).\n"
        "- Use lowercase for category labels.\n"
        "- Provide Polish and English equivalents for each category.\n"
        "- Prefer generic intent-level labels (e.g. social media, chat, shopping, banking, maps, game).\n"
        "- Do not invent categories unrelated to visible content.\n"
        "- summary_pl and summary_en should be one short sentence each.\n"
        "- Do not transcribe text from the image.\n"
        "- Do not copy exact long strings, code blocks, or IDs from the image.\n"
        "- Use abstract description only, e.g. 'very long alphanumeric string'.\n"
        "- Do not output markdown.\n"
        f"- Language hint for visible text: {language_hint}.\n"
        f"{app_hint_line}"
    )


def parse_category_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary_pl = str(payload.get("summary_pl", "") or "").strip()
    summary_en = str(payload.get("summary_en", "") or "").strip()

    categories_raw = payload.get("categories", [])
    if not isinstance(categories_raw, list):
        raise ValueError("response field 'categories' is not a list")

    categories: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in categories_raw:
        if not isinstance(item, Mapping):
            raise ValueError("category item is not an object")
        pl_value = str(item.get("pl", "") or "").strip().lower()
        en_value = str(item.get("en", "") or "").strip().lower()
        if not pl_value or not en_value:
            continue
        pair = (pl_value, en_value)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        categories.append({"pl": pl_value, "en": en_value})

    if len(categories) > 7:
        categories = categories[:7]
    if len(categories) < 5:
        raise ValueError("response must contain at least 5 unique category pairs")

    if not summary_pl:
        summary_pl = ", ".join(item["pl"] for item in categories[:3])
    if not summary_en:
        summary_en = ", ".join(item["en"] for item in categories[:3])

    return {
        "summary_pl": summary_pl,
        "summary_en": summary_en,
        "categories": categories,
    }


@dataclass(frozen=True, slots=True)
class CategoryLabel:
    pl: str
    en: str


@dataclass(frozen=True, slots=True)
class VisionEngineResult:
    engine_name: str
    summary_pl: str
    summary_en: str
    categories: list[CategoryLabel]
    app_hint: str | None = None


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
        client: httpx.Client | None = None,
    ) -> None:
        self._api_base_url = api_base_url
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._keep_alive = keep_alive
        self._think = think
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
        prompt = build_category_prompt(
            language_hint=language_hint,
            app_hint_from_filename=app_hint_from_filename,
        )
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
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
            "format": {
                "type": "object",
                "properties": {
                    "summary_pl": {"type": "string"},
                    "summary_en": {"type": "string"},
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pl": {"type": "string"},
                                "en": {"type": "string"},
                            },
                            "required": ["pl", "en"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["summary_pl", "summary_en", "categories"],
                "additionalProperties": False,
            },
            "options": build_ollama_options_payload(
                temperature=self._temperature,
                max_output_tokens=self._max_output_tokens,
                ollama_num_predict=None,
                ollama_num_ctx=None,
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
        response_payload = response.json()
        message = response_payload.get("message", {})
        if not isinstance(message, Mapping):
            raise ValueError("missing 'message' in Ollama response")
        raw_content = str(message.get("content", "")).strip()
        parsed = parse_category_response(extract_json_object_from_text(raw_content))
        return _build_vision_engine_result(
            engine_name="ollama",
            parsed=parsed,
            app_hint=app_hint_from_filename or None,
        )


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
        client: httpx.Client | None = None,
    ) -> None:
        self._engine_name = engine_name
        self._api_base_url = api_base_url
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
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
        prompt = build_category_prompt(
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
                    "name": "screenshot_categories",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary_pl": {"type": "string"},
                            "summary_en": {"type": "string"},
                            "categories": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "pl": {"type": "string"},
                                        "en": {"type": "string"},
                                    },
                                    "required": ["pl", "en"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["summary_pl", "summary_en", "categories"],
                        "additionalProperties": False,
                    },
                },
            },
        }
        if self._max_output_tokens is not None:
            payload["max_tokens"] = self._max_output_tokens

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
        parsed = parse_category_response(extract_json_object_from_text(raw_content))
        return _build_vision_engine_result(
            engine_name=self._engine_name,
            parsed=parsed,
            app_hint=app_hint_from_filename or None,
        )


def _build_vision_engine_result(
    *,
    engine_name: str,
    parsed: dict[str, Any],
    app_hint: str | None,
) -> VisionEngineResult:
    return VisionEngineResult(
        engine_name=engine_name,
        summary_pl=str(parsed["summary_pl"]),
        summary_en=str(parsed["summary_en"]),
        categories=[
            CategoryLabel(pl=str(item["pl"]), en=str(item["en"]))
            for item in parsed["categories"]
        ],
        app_hint=app_hint,
    )


def _image_bytes_to_data_url(*, image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"


def _ocr_excerpt_line(ocr_text: str) -> str:
    excerpt = ocr_text.strip()
    if not excerpt:
        return ""
    return f'\n- OCR excerpt: "{excerpt[:500]}". Treat it as supporting context, not the only source of truth.\n'
