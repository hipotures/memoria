from __future__ import annotations

from memoria.llm_utils import build_ollama_options_payload
from memoria.llm_utils import build_ollama_reasoning_payload
from memoria.llm_utils import extract_message_content_text
from memoria.llm_utils import normalize_openai_api_base_url
from memoria.llm_utils import strip_v1_suffix
from memoria.vision.engines import build_category_prompt
from memoria.vision.engines import extract_app_hint_from_filename
from memoria.vision.engines import parse_category_response


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


def test_build_category_prompt_contains_schema_and_hint() -> None:
    prompt = build_category_prompt(language_hint="pl,en", app_hint_from_filename="TikTok")
    assert '"summary_pl"' in prompt
    assert '"summary_en"' in prompt
    assert '"categories"' in prompt
    assert "5 to 7 unique category pairs" in prompt
    assert "Filename app hint" in prompt
    assert "TikTok" in prompt
    assert "Do not transcribe text from the image." in prompt


def test_parse_category_response_normalizes_and_deduplicates() -> None:
    payload = {
        "summary_pl": "",
        "summary_en": "",
        "categories": [
            {"pl": "Media Społecznościowe", "en": "Social Media"},
            {"pl": "Wideo", "en": "Video"},
            {"pl": "Komentarze", "en": "Comments"},
            {"pl": "Profil", "en": "Profile"},
            {"pl": "powiadomienia", "en": "Notifications"},
            {"pl": "wideo", "en": "video"},
        ],
    }

    parsed = parse_category_response(payload)
    assert len(parsed["categories"]) == 5
    assert parsed["summary_pl"] == "media społecznościowe, wideo, komentarze"
    assert parsed["summary_en"] == "social media, video, comments"
