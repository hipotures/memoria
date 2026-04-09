from __future__ import annotations

from pathlib import Path

from memoria.runtime_settings import load_runtime_settings_from_env


def test_load_runtime_settings_reads_values_from_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MEMORIA_OCR_ENGINE", raising=False)
    monkeypatch.delenv("MEMORIA_PADDLE_LANG", raising=False)
    monkeypatch.delenv("MEMORIA_VISION_ENGINE", raising=False)
    monkeypatch.delenv("MEMORIA_VISION_MODEL", raising=False)
    monkeypatch.delenv("MEMORIA_OLLAMA_THINK", raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MEMORIA_OCR_ENGINE=paddleocr",
                "MEMORIA_PADDLE_LANG=pl",
                "MEMORIA_VISION_ENGINE=ollama",
                "MEMORIA_VISION_MODEL=qwen3.5:9b",
                "MEMORIA_OLLAMA_THINK=high",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings_from_env()

    assert settings.ocr_engine == "paddleocr"
    assert settings.paddle_lang == "pl"
    assert settings.vision_engine == "ollama"
    assert settings.vision_model == "qwen3.5:9b"
    assert settings.ollama_think == "high"


def test_process_environment_overrides_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEMORIA_VISION_MODEL", "env-model")

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MEMORIA_VISION_MODEL=dotenv-model",
                "MEMORIA_VISION_ENGINE=ollama",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings_from_env()

    assert settings.vision_model == "env-model"
    assert settings.vision_engine == "ollama"
