from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv
from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    database_url: str = ""
    ocr_engine: str = "paddleocr"
    ocr_language_hint: str | None = None
    paddle_lang: str = "en"
    paddle_use_angle_cls: bool = True
    paddle_use_gpu: bool = False
    vision_engine: str = "ollama"
    vision_language_hint: str = "pl,en"
    vision_api_base_url: str = "http://127.0.0.1:11434"
    vision_model: str = "qwen3.5:9b"
    vision_temperature: float = 0.0
    vision_timeout_seconds: float = 60.0
    vision_max_output_tokens: int | None = 800
    ollama_keep_alive: str = "5m"
    ollama_think: str = "false"


def load_runtime_settings_from_env() -> RuntimeSettings:
    _load_dotenv_from_cwd()
    return RuntimeSettings(
        database_url=os.getenv("MEMORIA_DATABASE_URL", _default_database_url()),
        ocr_engine=os.getenv("MEMORIA_OCR_ENGINE", "paddleocr"),
        ocr_language_hint=_env_or_none("MEMORIA_OCR_LANGUAGE_HINT"),
        paddle_lang=os.getenv("MEMORIA_PADDLE_LANG", "en"),
        paddle_use_angle_cls=_env_bool("MEMORIA_PADDLE_USE_ANGLE_CLS", True),
        paddle_use_gpu=_env_bool("MEMORIA_PADDLE_USE_GPU", False),
        vision_engine=os.getenv("MEMORIA_VISION_ENGINE", "ollama"),
        vision_language_hint=os.getenv("MEMORIA_VISION_LANGUAGE_HINT", "pl,en"),
        vision_api_base_url=os.getenv("MEMORIA_VISION_API_BASE_URL", "http://127.0.0.1:11434"),
        vision_model=os.getenv("MEMORIA_VISION_MODEL", "qwen3.5:9b"),
        vision_temperature=float(os.getenv("MEMORIA_VISION_TEMPERATURE", "0.0")),
        vision_timeout_seconds=float(os.getenv("MEMORIA_VISION_TIMEOUT_SECONDS", "60.0")),
        vision_max_output_tokens=_env_int_or_none("MEMORIA_VISION_MAX_OUTPUT_TOKENS", 800),
        ollama_keep_alive=os.getenv("MEMORIA_OLLAMA_KEEP_ALIVE", "5m"),
        ollama_think=os.getenv("MEMORIA_OLLAMA_THINK", "false"),
    )


def _load_dotenv_from_cwd() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=Path(dotenv_path), override=False)


def _default_database_url() -> str:
    return f"sqlite:///{Path.cwd() / 'data' / 'memoria.db'}"


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int_or_none(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    stripped = raw.strip().lower()
    if stripped in {"", "none", "null"}:
        return None
    return int(stripped)
