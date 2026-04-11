from __future__ import annotations

from memoria.ocr.engines import OcrEngine
from memoria.ocr.engines import PaddleOcrEngine
from memoria.runtime_settings import RuntimeSettings
from memoria.vision.engines import OllamaVisionEngine
from memoria.vision.engines import OpenAICompatibleVisionEngine
from memoria.vision.engines import VisionEngine


def create_ocr_engine(settings: RuntimeSettings) -> OcrEngine:
    if settings.ocr_engine == "paddleocr":
        return PaddleOcrEngine(
            lang=settings.paddle_lang,
            use_angle_cls=settings.paddle_use_angle_cls,
            use_gpu=settings.paddle_use_gpu,
        )
    raise ValueError(f"unsupported OCR engine: {settings.ocr_engine}")


def create_vision_engine(settings: RuntimeSettings) -> VisionEngine:
    if settings.vision_engine == "ollama":
        return OllamaVisionEngine(
            api_base_url=settings.vision_api_base_url,
            model=settings.vision_model,
            temperature=settings.vision_temperature,
            timeout_seconds=settings.vision_timeout_seconds,
            max_output_tokens=settings.vision_max_output_tokens,
            keep_alive=settings.ollama_keep_alive,
            think=settings.ollama_think,
            seed=settings.seed,
        )
    if settings.vision_engine in {"vllm", "llamacpp"}:
        return OpenAICompatibleVisionEngine(
            engine_name=settings.vision_engine,
            api_base_url=settings.vision_api_base_url,
            model=settings.vision_model,
            temperature=settings.vision_temperature,
            timeout_seconds=settings.vision_timeout_seconds,
            max_output_tokens=settings.vision_max_output_tokens,
            seed=settings.seed,
        )
    raise ValueError(f"unsupported vision engine: {settings.vision_engine}")
