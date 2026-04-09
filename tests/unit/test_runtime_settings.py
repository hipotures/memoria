from __future__ import annotations

from pathlib import Path

from memoria.runtime_settings import load_runtime_settings_from_env


def test_load_runtime_settings_reads_values_from_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MEMORIA_DATABASE_URL", raising=False)
    monkeypatch.delenv("MEMORIA_OCR_ENGINE", raising=False)
    monkeypatch.delenv("MEMORIA_PADDLE_LANG", raising=False)
    monkeypatch.delenv("MEMORIA_VISION_ENGINE", raising=False)
    monkeypatch.delenv("MEMORIA_VISION_MODEL", raising=False)
    monkeypatch.delenv("MEMORIA_OLLAMA_THINK", raising=False)
    monkeypatch.delenv("MEMORIA_SEED", raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MEMORIA_DATABASE_URL=sqlite:////tmp/memoria-from-dotenv.db",
                "MEMORIA_OCR_ENGINE=paddleocr",
                "MEMORIA_PADDLE_LANG=pl",
                "MEMORIA_VISION_ENGINE=ollama",
                "MEMORIA_VISION_MODEL=qwen3.5:9b",
                "MEMORIA_OLLAMA_THINK=high",
                "MEMORIA_SEED=99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings_from_env()

    assert settings.database_url == "sqlite:////tmp/memoria-from-dotenv.db"
    assert settings.ocr_engine == "paddleocr"
    assert settings.paddle_lang == "pl"
    assert settings.vision_engine == "ollama"
    assert settings.vision_model == "qwen3.5:9b"
    assert settings.ollama_think == "high"
    assert settings.seed == 99


def test_process_environment_overrides_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEMORIA_DATABASE_URL", "sqlite:////tmp/memoria-from-env.db")
    monkeypatch.setenv("MEMORIA_VISION_MODEL", "env-model")
    monkeypatch.setenv("MEMORIA_SEED", "123")

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MEMORIA_DATABASE_URL=sqlite:////tmp/memoria-from-dotenv.db",
                "MEMORIA_VISION_MODEL=dotenv-model",
                "MEMORIA_VISION_ENGINE=ollama",
                "MEMORIA_SEED=77",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings_from_env()

    assert settings.database_url == "sqlite:////tmp/memoria-from-env.db"
    assert settings.vision_model == "env-model"
    assert settings.vision_engine == "ollama"
    assert settings.seed == 123


def test_load_runtime_settings_uses_repo_local_database_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MEMORIA_DATABASE_URL", raising=False)
    monkeypatch.delenv("MEMORIA_SEED", raising=False)

    settings = load_runtime_settings_from_env()

    assert settings.database_url == f"sqlite:///{tmp_path / 'data' / 'memoria.db'}"
    assert settings.seed == 42


def test_load_runtime_settings_preserves_zero_seed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEMORIA_SEED", "0")

    settings = load_runtime_settings_from_env()

    assert settings.seed == 0
