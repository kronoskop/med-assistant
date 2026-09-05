from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class ErrorBody(BaseModel):
    code: str
    message: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be empty")
        return value


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False


class SourceFragment(BaseModel):
    """Фрагмент документа основы, подтверждающий утверждение ответа."""

    id: str
    document_id: str
    document_title: str
    origin: str
    revision: str
    language: str
    location: str
    text: str
    kind: str = "prose"  # prose | table
    url: str | None = None


class SupportDocument(BaseModel):
    """Документ подкрепления: ориентир со ссылкой, без цитат и без сносок."""

    document_id: str
    title: str
    origin: str
    revision: str
    url: str


class ChatResponse(BaseModel):
    message: ChatMessage
    disclaimer: str
    # Ниже — аддитивные поля: существующие клиенты их просто не читают.
    grounded: bool = True
    grounding: str = "grounded"
    sources: list[SourceFragment] = Field(default_factory=list)
    support: list[SupportDocument] = Field(default_factory=list)
