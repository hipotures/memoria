from __future__ import annotations

from memoria.llm_utils import build_ollama_options_payload
from memoria.llm_utils import build_ollama_reasoning_payload
from memoria.llm_utils import extract_message_content_text
from memoria.llm_utils import normalize_openai_api_base_url
from memoria.llm_utils import strip_v1_suffix
from memoria.vision.engines import OllamaVisionEngine
from memoria.vision.engines import build_interpretation_prompt
from memoria.vision.engines import extract_app_hint_from_filename
from memoria.vision.engines import parse_interpretation_response


def test_strip_v1_suffix_handles_openai_compat_url() -> None:
    assert strip_v1_suffix("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert strip_v1_suffix("http://127.0.0.1:11434/v1/") == "http://127.0.0.1:11434"


def test_normalize_openai_api_base_url() -> None:
    assert normalize_openai_api_base_url("http://127.0.0.1:8001/v1") == "http://127.0.0.1:8001"
    assert normalize_openai_api_base_url("http://127.0.0.1:8001") == "http://127.0.0.1:8001"


def test_extract_message_content_text_from_openai_parts() -> None:
    content = [
        {"type": "output_text", "text": '{"summary_pl":"x"'},
        {"type": "output_text", "text": ',"summary_en":"y","categories":[]}'},
    ]
    text = extract_message_content_text(content)
    assert text == '{"summary_pl":"x"\n,"summary_en":"y","categories":[]}'


def test_build_ollama_reasoning_payload_for_levels() -> None:
    assert build_ollama_reasoning_payload("inherit") == {}
    assert build_ollama_reasoning_payload("false") == {
        "think": False,
        "reasoning_effort": "none",
        "reasoning": {"effort": "none"},
    }
    assert build_ollama_reasoning_payload("true") == {"think": True}


def test_build_ollama_options_payload_prefers_num_predict_override() -> None:
    options = build_ollama_options_payload(
        temperature=0.0,
        max_output_tokens=4096,
        ollama_num_predict=2048,
        ollama_num_ctx=8192,
        seed=42,
    )
    assert options == {"temperature": 0.0, "num_predict": 2048, "num_ctx": 8192, "seed": 42}


def test_extract_app_hint_from_filename_for_phone_screenshot() -> None:
    assert extract_app_hint_from_filename("Screenshot_20250822_122853_TikTok.jpg") == "TikTok"
    assert extract_app_hint_from_filename("Screenshot_20251115_143557_Instagram~2.jpg") == "Instagram"
    assert extract_app_hint_from_filename("Screenshot From 2025-01-02 15-07-41.png") == ""


def test_build_interpretation_prompt_contains_schema_and_hint() -> None:
    prompt = build_interpretation_prompt(language_hint="pl,en", app_hint_from_filename="TikTok")
    assert '"screen_category"' in prompt
    assert '"semantic_summary"' in prompt
    assert '"topic_candidates"' in prompt
    assert '"entity_mentions"' in prompt
    assert '"searchable_labels"' in prompt
    assert "Filename app hint" in prompt
    assert "TikTok" in prompt
    assert "Return exactly one JSON object" in prompt
    assert "At most 3 topic_candidates" in prompt
    assert "At most 6 entity_mentions" in prompt
    assert "At most 8 searchable_labels" in prompt


def test_parse_interpretation_response_normalizes_and_deduplicates() -> None:
    payload = {
        "screen_category": "chat",
        "semantic_summary": "Telegram chat about booking train tickets for Berlin.",
        "app_hint": "Telegram",
        "topic_candidates": [
            {"slug": "trip-to-berlin", "title": "Trip to Berlin", "confidence": 0.95},
            {"slug": "trip-to-berlin", "title": "Trip to Berlin", "confidence": 0.91},
        ],
        "task_candidates": [
            {"slug": "book-train", "title": "Book Train", "confidence": 0.89},
        ],
        "person_candidates": [
            {"slug": "alice", "title": "Alice", "confidence": 0.62},
        ],
        "entity_mentions": [
            {"type": "person", "text": "Alice", "confidence": 0.82},
            {"type": "person", "text": "Alice", "confidence": 0.70},
        ],
        "searchable_labels": ["telegram", "berlin", "telegram"],
        "cluster_hints": ["travel", "chat", "travel"],
        "confidence": {
            "screen_category": 0.91,
            "semantic_summary": 0.88,
            "topic_candidates": 0.95,
        },
    }

    parsed = parse_interpretation_response(payload)
    assert parsed["screen_category"] == "chat"
    assert parsed["semantic_summary"] == "Telegram chat about booking train tickets for Berlin."
    assert parsed["app_hint"] == "telegram"
    assert parsed["topic_candidates"] == [
        {"confidence": 0.95, "slug": "trip-to-berlin", "title": "Trip to Berlin"}
    ]
    assert parsed["task_candidates"] == [
        {"confidence": 0.89, "slug": "book-train", "title": "Book Train"}
    ]
    assert parsed["person_candidates"] == [
        {"confidence": 0.62, "slug": "alice", "title": "Alice"}
    ]
    assert parsed["entity_mentions"] == [
        {"confidence": 0.82, "text": "Alice", "type": "person"}
    ]
    assert parsed["searchable_labels"] == ["telegram", "berlin"]
    assert parsed["cluster_hints"] == ["travel", "chat"]
    assert parsed["confidence"] == {
        "screen_category": 0.91,
        "semantic_summary": 0.88,
        "topic_candidates": 0.95,
    }


def test_parse_interpretation_response_repairs_legacy_category_strings_from_failed_tiktok_case() -> None:
    payload = {
        "summary_pl": "Zrzut ekranu z TikToka z live i pytaniami.",
        "summary_en": "TikTok live screenshot with questions and answers.",
        "categories": [
            "social media",
            "video",
            "live",
            "questions",
            "answers",
        ],
    }

    parsed = parse_interpretation_response(payload)
    assert parsed["screen_category"] == "generic"
    assert parsed["semantic_summary"] == "TikTok live screenshot with questions and answers."
    assert parsed["searchable_labels"] == [
        "social media",
        "video",
        "live",
        "questions",
        "answers",
    ]
    assert parsed["cluster_hints"] == parsed["searchable_labels"]
    assert parsed["topic_candidates"] == []
    assert parsed["task_candidates"] == []


def test_ollama_vision_engine_retries_with_higher_token_limit_when_response_is_truncated() -> None:
    client = _RecordingClient(
        responses=[
            _FakeResponse(
                {
                    "message": {
                        "content": '{"screen_category":"maps","semantic_summary":"Truncated'
                    },
                    "done_reason": "length",
                }
            ),
            _FakeResponse(
                {
                    "message": {
                        "content": (
                            '{"screen_category":"maps","semantic_summary":"Map view.",'
                            '"app_hint":null,"topic_candidates":[],"task_candidates":[],'
                            '"person_candidates":[],"entity_mentions":[],"searchable_labels":["map"],'
                            '"cluster_hints":["geography"],'
                            '"confidence":{"screen_category":0.9,"semantic_summary":0.8}}'
                        )
                    },
                    "done_reason": "stop",
                }
            ),
        ]
    )
    engine = OllamaVisionEngine(
        api_base_url="http://127.0.0.1:11434",
        model="qwen3.5:9b",
        max_output_tokens=800,
        client=client,
    )

    result = engine.analyze(
        image_bytes=b"test-image",
        media_type="image/png",
        language_hint="pl,en",
        app_hint_from_filename="TikTok",
        ocr_text="Map labels and park names.",
    )

    assert result.screen_category == "maps"
    assert result.semantic_summary == "Map view."
    assert len(client.requests) == 2
    assert client.requests[0]["options"]["num_predict"] == 800
    assert client.requests[1]["options"]["num_predict"] == 1600


def test_ollama_vision_engine_retries_multiple_times_until_truncation_stops() -> None:
    client = _RecordingClient(
        responses=[
            _FakeResponse(
                {
                    "message": {
                        "content": '{"screen_category":"maps","semantic_summary":"First truncation'
                    },
                    "done_reason": "length",
                }
            ),
            _FakeResponse(
                {
                    "message": {
                        "content": '{"screen_category":"maps","semantic_summary":"Second truncation'
                    },
                    "done_reason": "length",
                }
            ),
            _FakeResponse(
                {
                    "message": {
                        "content": (
                            '{"screen_category":"maps","semantic_summary":"Large map view.",'
                            '"app_hint":null,"topic_candidates":[],"task_candidates":[],'
                            '"person_candidates":[],"entity_mentions":[],"searchable_labels":["map"],'
                            '"cluster_hints":["geography"],'
                            '"confidence":{"screen_category":0.9,"semantic_summary":0.8}}'
                        )
                    },
                    "done_reason": "stop",
                }
            ),
        ]
    )
    engine = OllamaVisionEngine(
        api_base_url="http://127.0.0.1:11434",
        model="qwen3.5:9b",
        max_output_tokens=800,
        client=client,
    )

    result = engine.analyze(
        image_bytes=b"test-image",
        media_type="image/png",
        language_hint="pl,en",
        app_hint_from_filename="TikTok",
        ocr_text="Dense map labels and region names.",
    )

    assert result.semantic_summary == "Large map view."
    assert len(client.requests) == 3
    assert client.requests[0]["options"]["num_predict"] == 800
    assert client.requests[1]["options"]["num_predict"] == 1600
    assert client.requests[2]["options"]["num_predict"] == 3200


class _RecordingClient:
    def __init__(self, *, responses: list["_FakeResponse"]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, json: dict[str, object]) -> "_FakeResponse":
        self.requests.append(json)
        return self._responses.pop(0)


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"unexpected HTTP {self.status_code}")
