from pydantic import BaseModel


class IngestScreenshotRequest(BaseModel):
    filename: str
    media_type: str
    connector_instance_id: str
    content_base64: str
    external_id: str | None = None
    ocr_text: str | None = None


class AssistantQueryRequest(BaseModel):
    question: str
