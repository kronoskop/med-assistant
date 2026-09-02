from collections.abc import AsyncIterator

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.prompt import SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings, get_settings


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        kwargs: dict = {
            "base_url": settings.lmstudio_base_url,
            "api_key": settings.lmstudio_api_key,
            "timeout": settings.lmstudio_timeout_seconds,
        }
        if http_client is not None:
            kwargs["http_client"] = http_client
        self._client = AsyncOpenAI(**kwargs)

    def build_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[message.model_dump() for message in messages],
        ]

    async def complete(self, messages: list[ChatMessage]) -> str:
        response = await self._create(messages, stream=False)
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise AppError(502, "llm_error", "Модель вернула пустой ответ")
        return content

    async def start_chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._create(messages, stream=True)

        async def tokens() -> AsyncIterator[str]:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = delta.content if delta is not None else None
                if text:
                    yield text

        return tokens()

    async def ping(self) -> None:
        try:
            await self._client.models.list()
        except (APITimeoutError, httpx.TimeoutException) as exc:
            raise AppError(504, "llm_timeout", "Превышено время ожидания ответа модели") from exc
        except (APIConnectionError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен") from exc
        except APIStatusError as exc:
            raise AppError(502, "llm_error", "Ошибка языковой модели") from exc

    async def _create(self, messages: list[ChatMessage], stream: bool):
        try:
            return await self._client.chat.completions.create(
                model=self._settings.lmstudio_model,
                messages=self.build_messages(messages),
                temperature=0.2,
                stream=stream,
            )
        except (APITimeoutError, httpx.TimeoutException) as exc:
            raise AppError(504, "llm_timeout", "Превышено время ожидания ответа модели") from exc
        except (APIConnectionError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен") from exc
        except APIStatusError as exc:
            raise AppError(502, "llm_error", "Ошибка языковой модели") from exc


def get_llm() -> LLMClient:
    return LLMClient(get_settings())
