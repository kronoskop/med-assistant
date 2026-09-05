from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
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

from app.prompt import GROUNDING_INSTRUCTION, QUESTIONS_INSTRUCTION, SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings, get_settings

CHAT_SIGNATURE = (
    "conversation:string, fragments:string -> "
    "answer:string, sources:string[], questions?:json[], conflicts?:json[]"
)
# `?` — уточнения необязательны для Ax: ответ не должен пропасть целиком из-за
# того, что модель не выдала второстепенное поле. Схеме на проводе они всё
# равно предписаны, поэтому обычно приходят.
AxTransport = Callable[[dict[str, Any]], Any]

reasoning_logger = logging.getLogger("app.reasoning")


@dataclass(frozen=True)
class Answer:
    """Ответ программы: текст и всё, что модель к нему заявила.

    Заявленные — не значит подтверждённые: и источники, и уточнения сверяются
    с реально отобранными фрагментами выше по стеку. Уточнения и противоречия
    остаются здесь сырыми: разбирать их — дело границы доверия, а не транспорта.
    """

    text: str
    source_ids: tuple[str, ...] = ()
    questions: tuple[Any, ...] = ()
    conflicts: tuple[Any, ...] = ()


@dataclass
class Claims:
    """Заявленное моделью в потоке: наполняется по его завершении.

    В потоке текст идёт первым, а поля со ссылками — последними: собрать их
    можно только когда JSON дочитан до конца.
    """

    source_ids: list[str] = field(default_factory=list)
    questions: list[Any] = field(default_factory=list)
    conflicts: list[Any] = field(default_factory=list)


_JSON_TYPES = {
    "string": "string",
    "number": "number",
    "boolean": "boolean",
}

# Составные поля описываются явно: `json` в сигнатуре говорит Ax, что значение
# произвольной формы, но сервер модели ограничивает генерацию грамматикой и
# требует конкретных свойств.
_OBJECT_ITEMS = {
    "questions": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["question", "source"],
        "additionalProperties": False,
    },
    "conflicts": {
        "type": "object",
        "properties": {
            "first": {"type": "string"},
            "second": {"type": "string"},
        },
        "required": ["first", "second"],
        "additionalProperties": False,
    },
}


def response_schema(signature: str = CHAT_SIGNATURE) -> dict[str, Any]:
    """Схема ответа по выходным полям сигнатуры программы.

    MedGemma — reasoning-модель: текстовая инструкция «верни JSON» её не
    удерживает, она отвечает рассуждением. Схему исполняет сервер модели,
    ограничивая генерацию грамматикой.
    """
    outputs = signature.split("->", 1)[1]
    properties: dict[str, Any] = {}
    for declaration in outputs.split(","):
        name, _, kind = declaration.strip().partition(":")
        name = name.rstrip("?")  # необязательность — договор с Ax, не со схемой
        if not name:
            continue
        kind = kind.strip()
        if kind.endswith("[]"):
            inner = kind[:-2]
            item = _OBJECT_ITEMS.get(name) if inner == "json" else {"type": _JSON_TYPES.get(inner, "string")}
            properties[name] = {"type": "array", "items": item or {"type": "string"}}
        else:
            properties[name] = {"type": _JSON_TYPES.get(kind, "string")}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "assistant_answer",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def merge_adjacent_roles(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Склеивает подряд идущие сообщения одной роли.

    Ax выносит инструкцию о форме ответа отдельным user-сообщением, из-за чего
    получается `system, user, user`. Шаблон Gemma требует чередования ролей и
    отвечает 400 `Conversation roles must alternate`.
    """
    merged: list[dict[str, Any]] = []
    for message in messages:
        if merged and merged[-1].get("role") == message.get("role"):
            previous = merged[-1]
            merged[-1] = {
                **previous,
                "content": f"{previous.get('content', '')}\n\n{message.get('content', '')}",
            }
            continue
        merged.append(dict(message))
    return merged


def _log_reasoning(settings: Settings, text: str | None) -> None:
    """Рассуждение — клинический текст о случае пациента, поэтому по умолчанию
    не пишется никуда и уходит в отдельный логгер, не в журнал обращений."""
    if not settings.log_model_reasoning or not text or not text.strip():
        return
    reasoning_logger.debug("reasoning: %s", text.strip())


def _reasoning_from_body(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    value = message.get("reasoning_content")
    return value if isinstance(value, str) else None


class LMStudioCompatibleClient(OpenAICompatibleClient):
    """Приводит исходящий запрос к виду, который принимают LM Studio и шаблон
    загруженной модели, не трогая сетевой слой Ax."""

    def __init__(self, *args: Any, settings: Settings, **kwargs: Any) -> None:
        self._settings = settings
        super().__init__(*args, **kwargs)

    def _request_json(self, endpoint: str, payload: dict[str, Any], **kwargs: Any):
        if isinstance(payload, dict) and "messages" in payload:
            payload = dict(payload)
            payload["messages"] = merge_adjacent_roles(payload["messages"])
            payload["response_format"] = response_schema()
        result = super()._request_json(endpoint, payload, **kwargs)
        if not kwargs.get("stream"):
            _log_reasoning(self._settings, _reasoning_from_body(result))
            return result
        if not self._settings.log_model_reasoning:
            return result
        return self._tee_reasoning(result)

    def _tee_reasoning(self, chunks: Any) -> Any:
        collected: list[str] = []
        for chunk in chunks:
            collected.append(_reasoning_from_sse(chunk))
            yield chunk
        _log_reasoning(self._settings, "".join(collected))


def _reasoning_from_sse(chunk: object) -> str:
    raw = chunk.decode("utf-8", "ignore") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
    out = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        for choice in parsed.get("choices") or []:
            delta = choice.get("delta") if isinstance(choice, dict) else None
            if isinstance(delta, dict) and isinstance(delta.get("reasoning_content"), str):
                out.append(delta["reasoning_content"])
    return "".join(out)


# Совместимость модели проверяется один раз и переспрашивается по таймауту:
# врач не должен узнавать о несовместимости из ошибки на свой первый вопрос,
# но и прогонять генерацию на каждый опрос готовности незачем.
_COMPAT_TTL_SECONDS = 60.0
_compat_ok_until = 0.0


def reset_compatibility_cache() -> None:
    global _compat_ok_until
    _compat_ok_until = 0.0


async def ensure_structured_output(llm: "LLMClient") -> None:
    global _compat_ok_until
    if time.monotonic() < _compat_ok_until:
        return
    await llm.check_structured_output()
    _compat_ok_until = time.monotonic() + _COMPAT_TTL_SECONDS


def format_conversation(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _make_program():
    return ax(
        CHAT_SIGNATURE,
        {
            "instruction": "\n".join(
                (SYSTEM_PROMPT, GROUNDING_INSTRUCTION, QUESTIONS_INSTRUCTION)
            ),
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
        self._ai = LMStudioCompatibleClient(
            settings=settings,
            api_key=settings.lmstudio_api_key,
            model=settings.lmstudio_model,
            base_url=settings.lmstudio_base_url,
            timeout=settings.lmstudio_timeout_seconds,
            transport=transport,
            model_config={"temperature": 0.2},
            model_info=[
                {
                    "name": settings.lmstudio_model,
                    # LM Studio принимает только `json_schema` и `text`. В режиме
                    # `text` Ax не выставляет response_format сам, и схему
                    # подставляет LMStudioCompatibleClient.
                    "supported": {"structuredOutputModes": ["text"]},
                }
            ],
        )

    def _inputs(self, messages: list[ChatMessage], fragments: str = "") -> dict[str, str]:
        return {
            "conversation": format_conversation(messages),
            "fragments": fragments or "Фрагменты не найдены.",
        }

    async def complete(self, messages: list[ChatMessage], fragments: str = "") -> Answer:
        program = _make_program()
        try:
            result = await asyncio.to_thread(
                program.forward,
                self._ai,
                self._inputs(messages, fragments),
            )
        except Exception as exc:
            raise _map_ax_error(exc) from exc
        answer = _answer_from_result(result)
        if answer is None or not answer.strip():
            raise AppError(502, "llm_error", "Модель вернула пустой ответ")
        return Answer(
            answer,
            _sources_from_result(result),
            _objects_from_result(result, "questions"),
            _objects_from_result(result, "conflicts"),
        )

    async def start_chat_stream(
        self,
        messages: list[ChatMessage],
        fragments: str = "",
        claims: Claims | None = None,
    ) -> AsyncIterator[str]:
        """`claims`, если передан, наполняется заявленным моделью по завершении
        потока: в JSON эти поля идут после текста ответа."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        program = _make_program()
        values = self._inputs(messages, fragments)

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
                    if claims is not None:
                        claims.source_ids.extend(_sources_from_result(buffer))
                        claims.questions.extend(_objects_from_result(buffer, "questions"))
                        claims.conflicts.extend(_objects_from_result(buffer, "conflicts"))
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

    async def check_structured_output(self) -> None:
        """Минимальный запрос со схемой ответа: принимает ли её модель.

        `max_tokens: 1` — проверяется не качество ответа, а то, что сервер
        модели вообще принимает ограниченную схемой генерацию.
        """
        url = self._settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self._settings.lmstudio_model,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
            "response_format": response_schema(),
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.lmstudio_timeout_seconds
                ) as client:
                    response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AppError(
                504, "llm_timeout", "Превышено время ожидания ответа модели"
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен") from exc
        except httpx.HTTPStatusError as exc:
            raise AppError(
                503,
                "model_incompatible",
                "Модель не принимает структурированный вывод по схеме: "
                f"загрузите в LM Studio модель с поддержкой structured output "
                f"(сейчас настроена {self._settings.lmstudio_model})",
            ) from exc

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


def _as_dict(result: object) -> dict[str, Any] | None:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return None
    return result if isinstance(result, dict) else None


def _sources_from_result(result: object) -> tuple[str, ...]:
    payload = _as_dict(result)
    if payload is None:
        return ()
    values = payload.get("sources")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return ()
    return tuple(str(v) for v in values if isinstance(v, (str, int)))


def _objects_from_result(result: object, key: str) -> tuple[Any, ...]:
    """Составные поля отдаются как есть: их достоверность проверяется выше."""
    payload = _as_dict(result)
    if payload is None:
        return ()
    values = payload.get(key)
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        return ()
    return tuple(values)


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
