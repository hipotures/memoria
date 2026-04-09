from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


def strip_v1_suffix(api_base_url: str) -> str:
    text = api_base_url.rstrip("/")
    if text.endswith("/v1"):
        return text[:-3]
    return text


def normalize_openai_api_base_url(api_base_url: str) -> str:
    return strip_v1_suffix(api_base_url)


def build_ollama_reasoning_payload(ollama_think: str) -> dict[str, Any]:
    if ollama_think == "inherit":
        return {}
    if ollama_think == "false":
        return {
            "think": False,
            "reasoning_effort": "none",
            "reasoning": {"effort": "none"},
        }
    if ollama_think == "true":
        return {"think": True}
    if ollama_think in {"low", "medium", "high"}:
        return {
            "think": True,
            "reasoning_effort": ollama_think,
            "reasoning": {"effort": ollama_think},
        }
    raise ValueError(f"unsupported ollama_think value: {ollama_think}")


def build_ollama_options_payload(
    *,
    temperature: float,
    max_output_tokens: int | None,
    ollama_num_predict: int | None,
    ollama_num_ctx: int | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {"temperature": temperature}
    if ollama_num_predict is not None:
        options["num_predict"] = ollama_num_predict
    elif max_output_tokens is not None:
        options["num_predict"] = max_output_tokens
    if ollama_num_ctx is not None:
        options["num_ctx"] = ollama_num_ctx
    return options


def extract_json_object_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty response body")

    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        payload = json.loads(fence_match.group(1))
        if isinstance(payload, dict):
            return payload

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        raise ValueError("no JSON object found in response")
    payload = json.loads(stripped[first_brace : last_brace + 1])
    if not isinstance(payload, dict):
        raise ValueError("parsed payload is not an object")
    return payload


def extract_message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, Mapping):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()
    return ""
