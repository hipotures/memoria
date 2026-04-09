from __future__ import annotations

from memoria.ocr.engines import build_ocr_prompt
from memoria.ocr.engines import build_paddle_init_kwargs
from memoria.ocr.engines import extract_json_object_from_text
from memoria.ocr.engines import extract_lines_from_result
from memoria.ocr.engines import parse_ocr_response


def test_build_ocr_prompt_contains_anti_hallucination_rules() -> None:
    prompt = build_ocr_prompt(language_hint="pl,en")
    assert "Do not translate" in prompt
    assert "Do not correct spelling" in prompt
    assert "JSON object and nothing else" in prompt
    assert '"full_text"' in prompt
    assert '"content_tags"' in prompt
    assert "Preserve technical tokens exactly" in prompt


def test_extract_json_object_from_text_supports_markdown_fence() -> None:
    text = """Sure.\n```json\n{"lines":["Ala ma kota"]}\n```\n"""
    payload = extract_json_object_from_text(text)
    assert payload == {"lines": ["Ala ma kota"]}


def test_parse_ocr_response_joins_lines() -> None:
    payload = {"full_text": "Ala ma kota\nNumer 221", "content_tags": ["ui", "panel"]}
    parsed = parse_ocr_response(payload)
    assert parsed["lines"] == ["Ala ma kota", "Numer 221"]
    assert parsed["text"] == "Ala ma kota\nNumer 221"
    assert parsed["content_tags"] == ["ui", "panel"]


def test_extract_lines_from_legacy_paddleocr_shape() -> None:
    raw = [
        [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], ("Hello", 0.95)],
            [[[0, 2], [1, 2], [1, 3], [0, 3]], ("World", 0.90)],
        ]
    ]
    lines = extract_lines_from_result(raw)

    assert [line["text"] for line in lines] == ["Hello", "World"]
    assert lines[0]["confidence"] == 0.95
    assert lines[1]["confidence"] == 0.90


def test_extract_lines_from_dict_shape() -> None:
    raw = {
        "rec_texts": ["Ala", "ma", "kota"],
        "rec_scores": [0.91, 0.89, 0.93],
        "dt_polys": [
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            [[0, 2], [1, 2], [1, 3], [0, 3]],
            [[0, 4], [1, 4], [1, 5], [0, 5]],
        ],
    }
    lines = extract_lines_from_result(raw)

    assert [line["text"] for line in lines] == ["Ala", "ma", "kota"]
    assert lines[2]["confidence"] == 0.93


def test_build_paddle_init_kwargs_modern_api_without_use_gpu() -> None:
    supported = {"lang", "use_textline_orientation", "device"}
    kwargs = build_paddle_init_kwargs(
        supported_params=supported,
        lang="en",
        use_angle_cls=True,
        use_gpu=True,
    )

    assert kwargs == {
        "lang": "en",
        "use_textline_orientation": True,
        "device": "gpu",
    }
