from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from axllm import (
    AxAIServiceAuthenticationError,
    AxAIServiceError,
    AxAIServiceNetworkError,
    AxAIServiceStatusError,
    AxAIServiceTimeoutError,
    AxValidationError,
    OpenAICompatibleClient,
    ax,
)

from app.prompt import SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings, get_settings

CHAT_SIGNATURE = "conversation:string -> answer:string"
AxTransport = Callable[[dict[str, Any]], Any]


def format_conversation(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _make_program():
    return ax(
        CHAT_SIGNATURE,
        {
            "instruction": SYSTEM_PROMPT,
            "infra_retries": 0,
            "validation_retries": 0,
        },
    )


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        transport: AxTransport | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._ai = OpenAICompatibleClient(
            api_key=settings.lmstudio_api_key,
            model=settings.lmstudio_model,
            base_url=settings.lmstudio_base_url,
            timeout=settings.lmstudio_timeout_seconds,
            transport=transport,
            model_config={"temperature": 0.2},
            model_info=[
                {
                    "name": settings.lmstudio_model,
                    "supported": {"structuredOutputModes": ["json_object"]},
                }
            ],
        )

    def _inputs(self, messages: list[ChatMessage]) -> dict[str, str]:
        return {"conversation": format_conversation(messages)}

    async def complete(self, messages: list[ChatMessage]) -> str:
        program = _make_program()
        try:
            result = await asyncio.to_thread(
                program.forward,
                self._ai,
                self._inputs(messages),
            )
        except Exception as exc:
            raise _map_ax_error(exc) from exc
        answer = _answer_from_result(result)
        if answer is None or not answer.strip():
            raise AppError(502, "llm_error", "Модель вернула пустой ответ")
        return answer

    async def start_chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        program = _make_program()
        values = self._inputs(messages)

        def run() -> None:
            try:
                for event in program.streaming_forward(self._ai, values):
                    loop.call_soon_threadsafe(queue.put_nowait, ("event", event))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        threading.Thread(target=run, daemon=True).start()
        first = await queue.get()
        if first[0] == "error":
            raise _map_ax_error(first[1]) from first[1]

        async def tokens() -> AsyncIterator[str]:
            pending: list[tuple[str, object]] = [first]
            buffer = ""
            emitted = 0

            while True:
                kind, payload = pending.pop(0) if pending else await queue.get()
                if kind == "error":
                    raise _map_ax_error(payload) from payload
                if kind == "done":
                    answer = _parse_answer(buffer)
                    if answer is None or not answer.strip():
                        raise AppError(502, "llm_error", "Модель вернула пустой ответ")
                    leftover = answer[emitted:]
                    if leftover:
                        yield leftover
                    return
                buffer += _content_from_event(payload)
                partial = _parse_answer(buffer)
                if partial is not None and len(partial) > emitted:
                    chunk = partial[emitted:]
                    emitted = len(partial)
                    if chunk:
                        yield chunk

        return tokens()

    async def ping(self) -> None:
        url = self._settings.lmstudio_base_url.rstrip("/") + "/models"
        try:
            if self._http_client is not None:
                response = await self._http_client.get(url)
                response.raise_for_status()
                return
            async with httpx.AsyncClient(
                timeout=self._settings.lmstudio_timeout_seconds
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AppError(
                504, "llm_timeout", "Превышено время ожидания ответа модели"
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен") from exc
        except httpx.HTTPStatusError as exc:
            raise AppError(502, "llm_error", "Ошибка языковой модели") from exc


def get_llm() -> LLMClient:
    return LLMClient(get_settings())


def _answer_from_result(result: object) -> str | None:
    if isinstance(result, dict) and "answer" in result:
        value = result["answer"]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if isinstance(result, str):
        return _parse_answer(result)
    return None


def _content_from_event(event: object) -> str:
    if not isinstance(event, dict):
        return str(event) if event is not None else ""
    parts: list[str] = []
    for result in event.get("results") or []:
        if isinstance(result, dict):
            parts.append(str(result.get("content") or ""))
    if parts:
        return "".join(parts)
    data = event.get("data") if isinstance(event.get("data"), dict) else event
    if not isinstance(data, dict):
        return ""
    return str(
        data.get("delta")
        or data.get("content")
        or data.get("text")
        or ""
    )


def _parse_answer(buffer: str) -> str | None:
    text = buffer.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _partial_answer(text)
    if isinstance(data, dict) and "answer" in data:
        value = data["answer"]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return None


def _partial_answer(text: str) -> str | None:
    marker = '"answer"'
    start = text.find(marker)
    if start < 0:
        return None
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return None
    rest = text[colon + 1 :].lstrip()
    if not rest.startswith('"'):
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(rest)
    except json.JSONDecodeError:
        return _unfinished_json_string(rest[1:])
    return value if isinstance(value, str) else None


def _unfinished_json_string(raw: str) -> str:
    out: list[str] = []
    escaped = False
    for char in raw:
        if escaped:
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(char, char))
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            break
        out.append(char)
    return "".join(out)


def _map_ax_error(exc: object) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, (AxAIServiceTimeoutError, TimeoutError, httpx.TimeoutException)):
        return AppError(504, "llm_timeout", "Превышено время ожидания ответа модели")
    if isinstance(
        exc,
        (AxAIServiceNetworkError, OSError, httpx.ConnectError, httpx.ConnectTimeout),
    ):
        return AppError(503, "llm_unavailable", "LM Studio недоступен")
    if isinstance(exc, (AxAIServiceStatusError, AxAIServiceAuthenticationError)):
        return AppError(502, "llm_error", "Ошибка языковой модели")
    if isinstance(exc, (AxValidationError, json.JSONDecodeError, AxAIServiceError)):
        return AppError(502, "llm_error", "Ошибка языковой модели")
    return AppError(502, "llm_error", "Ошибка языковой модели")
