from __future__ import annotations

import asyncio
import json
import logging
import re
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

from app.prompt import (
    ANSWER_REMINDER,
    GROUNDING_INSTRUCTION,
    LANGUAGE_NAMES,
    QUESTIONS_INSTRUCTION,
    SYSTEM_PROMPT,
)
from app.schemas import AppError, ChatMessage
from app.settings import Settings, get_settings

ANSWER_SIGNATURE = "conversation:string, fragments:string -> answer:string"
# Уточнения и противоречия — отдельная короткая программа: ответ врачу не ждёт,
# пока модель допишет второстепенные поля, а их сбой не роняет ответ.
CLARIFY_SIGNATURE = "conversation:string, fragments:string -> questions?:json[], conflicts?:json[]"
# Ссылки на фрагменты отдельным полем не запрашиваются: они уже стоят в тексте
# ответа маркерами, и повторять их списком — лишние токены.
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
    reasoning_chars: int = 0


@dataclass
class Claims:
    """Заявленное моделью в потоке: наполняется по его завершении.

    В потоке текст идёт первым, а поля со ссылками — последними: собрать их
    можно только когда JSON дочитан до конца.
    """

    source_ids: list[str] = field(default_factory=list)
    questions: list[Any] = field(default_factory=list)
    conflicts: list[Any] = field(default_factory=list)
    reasoning_chars: int = 0
    clarify_ms: float | None = None


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


def response_schema(signature: str = ANSWER_SIGNATURE, schema_name: str = "assistant_answer") -> dict[str, Any]:
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
            "name": schema_name,
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


# Ax вставляет в системный промпт правило формы ответа для текстового режима
# («поле: значение по строкам») и тут же отдельным сообщением просит JSON.
# Форму держит схема на стороне сервера модели, поэтому противоречивое правило
# снимается: маленькой модели оно только мешает и стоит лишних токенов.
_FORMATTING_RULES = re.compile(r"\n*<formatting_rules>.*?</formatting_rules>\n*", re.S)


def strip_formatting_rules(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for message in messages:
        content = message.get("content")
        if message.get("role") == "system" and isinstance(content, str):
            message = {**message, "content": _FORMATTING_RULES.sub("\n", content).strip()}
        out.append(message)
    return out


class LMStudioCompatibleClient(OpenAICompatibleClient):
    """Приводит исходящий запрос к виду, который принимают LM Studio и шаблон
    загруженной модели, не трогая сетевой слой Ax.

    Один клиент — одна программа: у программы своя схема ответа и свой
    потолок длины. Клиент создаётся на запрос, поэтому счётчик рассуждения
    принадлежит одному запросу врача.
    """

    def __init__(
        self,
        *args: Any,
        settings: Settings,
        schema: dict[str, Any],
        max_tokens: int,
        **kwargs: Any,
    ) -> None:
        self._settings = settings
        self._schema = schema
        self._max_tokens = max_tokens
        self.reasoning_chars = 0
        super().__init__(*args, **kwargs)

    def _request_json(self, endpoint: str, payload: dict[str, Any], **kwargs: Any):
        if isinstance(payload, dict) and "messages" in payload:
            payload = dict(payload)
            payload["messages"] = merge_adjacent_roles(strip_formatting_rules(payload["messages"]))
            payload["response_format"] = self._schema
            payload.pop("max_completion_tokens", None)
            payload["max_tokens"] = self._max_tokens
        result = super()._request_json(endpoint, payload, **kwargs)
        if not kwargs.get("stream"):
            reasoning = _reasoning_from_body(result)
            self.reasoning_chars += len(reasoning or "")
            _log_reasoning(self._settings, reasoning)
            return result
        return self._tee_reasoning(result)

    def _tee_reasoning(self, chunks: Any) -> Any:
        # Длина рассуждения считается всегда — это число, не клинический текст;
        # сам текст собирается только при явно включённой отладке.
        keep = self._settings.log_model_reasoning
        collected: list[str] = []
        for chunk in chunks:
            piece = _reasoning_from_sse(chunk)
            self.reasoning_chars += len(piece)
            if keep:
                collected.append(piece)
            yield chunk
        if keep:
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


def _make_answer_program():
    return ax(
        ANSWER_SIGNATURE,
        {
            "instruction": "\n".join((SYSTEM_PROMPT, GROUNDING_INSTRUCTION)),
            "infra_retries": 0,
            "validation_retries": 0,
        },
    )


def _make_clarify_program():
    return ax(
        CLARIFY_SIGNATURE,
        {
            "instruction": "\n".join((SYSTEM_PROMPT, QUESTIONS_INSTRUCTION)),
            "infra_retries": 0,
            "validation_retries": 0,
        },
    )


clarify_logger = logging.getLogger("app.clarify")


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        transport: AxTransport | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._transport = transport
        self._ai = self._make_ai(response_schema(), settings.answer_max_tokens)
        self._clarify_ai = self._make_ai(
            response_schema(CLARIFY_SIGNATURE, "assistant_clarify"), settings.clarify_max_tokens
        )

    def _make_ai(self, schema: dict[str, Any], max_tokens: int) -> LMStudioCompatibleClient:
        settings = self._settings
        return LMStudioCompatibleClient(
            settings=settings,
            schema=schema,
            max_tokens=max_tokens,
            api_key=settings.lmstudio_api_key,
            model=settings.lmstudio_model,
            base_url=settings.lmstudio_base_url,
            timeout=settings.lmstudio_timeout_seconds,
            transport=self._transport,
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

    @property
    def reasoning_chars(self) -> int:
        return self._ai.reasoning_chars + self._clarify_ai.reasoning_chars

    def _inputs(self, messages: list[ChatMessage], fragments: str = "") -> dict[str, str]:
        return {
            "conversation": format_conversation(messages),
            "fragments": fragments or "Фрагменты не найдены.",
        }

    def _answer_inputs(self, values: dict[str, str], language: str | None) -> dict[str, str]:
        """Для ответа — напоминание о языке и номерах в самом конце фрагментов.
        Уточнениям оно не нужно: там своя форма ссылки."""
        if language not in LANGUAGE_NAMES:
            return values
        reminder = ANSWER_REMINDER.format(language=LANGUAGE_NAMES[language])
        return {**values, "fragments": f"{values['fragments']}\n\n{reminder}"}

    async def _clarify(self, values: dict[str, str]) -> tuple[tuple[Any, ...], tuple[Any, ...], float]:
        """Уточнения и противоречия. Сбой здесь не роняет ответ: уточнения
        дополняют ответ и не могут быть причиной его потери."""
        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(_make_clarify_program().forward, self._clarify_ai, values)
        except Exception as exc:  # noqa: BLE001 — любой сбой даёт пустые уточнения
            clarify_logger.warning("уточнения не получены: %s", _map_ax_error(exc).code)
            return (), (), round((time.perf_counter() - started) * 1000, 1)
        return (
            _objects_from_result(result, "questions"),
            _objects_from_result(result, "conflicts"),
            round((time.perf_counter() - started) * 1000, 1),
        )

    def _start_clarify(self, values: dict[str, str]) -> asyncio.Task | None:
        if self._settings.clarify_mode != "parallel":
            return None
        return asyncio.create_task(self._clarify(values))

    async def _finish_clarify(self, task: asyncio.Task | None, values: dict[str, str]):
        if task is not None:
            return await task
        if self._settings.clarify_mode == "after":
            return await self._clarify(values)
        return (), (), None

    async def complete(
        self, messages: list[ChatMessage], fragments: str = "", language: str | None = None
    ) -> Answer:
        values = self._inputs(messages, fragments)
        clarify = self._start_clarify(values)
        try:
            result = await asyncio.to_thread(
                _make_answer_program().forward, self._ai, self._answer_inputs(values, language)
            )
        except Exception as exc:
            if clarify is not None:
                clarify.cancel()
            raise _map_ax_error(exc) from exc
        answer = _answer_from_result(result)
        if answer is None or not answer.strip():
            if clarify is not None:
                clarify.cancel()
            raise AppError(502, "llm_error", "Модель вернула пустой ответ")
        questions, conflicts, _ = await self._finish_clarify(clarify, values)
        return Answer(
            answer,
            cited_ids(answer),
            questions,
            conflicts,
            self.reasoning_chars,
        )

    async def start_chat_stream(
        self,
        messages: list[ChatMessage],
        fragments: str = "",
        claims: Claims | None = None,
        language: str | None = None,
    ) -> AsyncIterator[str]:
        """`claims`, если передан, наполняется по завершении потока: ссылками
        из текста ответа и уточнениями из отдельной программы."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        program = _make_answer_program()
        values = self._inputs(messages, fragments)
        clarify = self._start_clarify(values)

        def run() -> None:
            try:
                for event in program.streaming_forward(self._ai, self._answer_inputs(values, language)):
                    loop.call_soon_threadsafe(queue.put_nowait, ("event", event))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        threading.Thread(target=run, daemon=True).start()
        first = await queue.get()
        if first[0] == "error":
            if clarify is not None:
                clarify.cancel()
            raise _map_ax_error(first[1]) from first[1]

        async def tokens() -> AsyncIterator[str]:
            pending: list[tuple[str, object]] = [first]
            reader = AnswerStream()
            try:
                while True:
                    kind, payload = pending.pop(0) if pending else await queue.get()
                    if kind == "error":
                        raise _map_ax_error(payload) from payload
                    if kind == "done":
                        answer = _parse_answer(reader.buffer)
                        if answer is None or not answer.strip():
                            raise AppError(502, "llm_error", "Модель вернула пустой ответ")
                        leftover = answer[reader.emitted :]
                        if leftover:
                            yield leftover
                        questions, conflicts, clarify_ms = await self._finish_clarify(clarify, values)
                        if claims is not None:
                            claims.source_ids.extend(cited_ids(answer))
                            claims.questions.extend(questions)
                            claims.conflicts.extend(conflicts)
                            claims.reasoning_chars = self.reasoning_chars
                            claims.clarify_ms = clarify_ms
                        return
                    chunk = reader.feed(_content_from_event(payload))
                    if chunk:
                        yield chunk
            finally:
                if clarify is not None and not clarify.done():
                    clarify.cancel()

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


# Ссылка внутри ответа: [document:язык:страница:порядок]
CITATION = re.compile(r"\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]")


def cited_ids(text: str) -> tuple[str, ...]:
    """Идентификаторы фрагментов в порядке первого упоминания в тексте."""
    return tuple(dict.fromkeys(CITATION.findall(text or "")))


class AnswerStream:
    """Достаёт текст поля `answer` из JSON, пока тот ещё пишется.

    Разбирает только новые символы: прежний способ перечитывал весь буфер на
    каждом токене, и длинный ответ стоил квадратично.
    """

    _ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/"}

    def __init__(self) -> None:
        self.buffer = ""
        self.emitted = 0
        self._pos = 0          # с какого символа буфера продолжать разбор
        self._inside = False   # внутри строки answer
        self._closed = False

    def feed(self, text: str) -> str:
        self.buffer += text
        if self._closed:
            return ""
        if not self._inside and not self._find_start():
            return ""
        out: list[str] = []
        buf, i = self.buffer, self._pos
        while i < len(buf):
            char = buf[i]
            if char == "\\":
                if i + 1 >= len(buf):
                    break  # продолжение escape придёт следующим токеном
                code = buf[i + 1]
                if code == "u":
                    decoded, size = _unicode_escape(buf, i)
                    if size == 0:
                        break  # escape ещё не дописан
                    out.append(decoded)
                    i += size
                    continue
                out.append(self._ESCAPES.get(code, code))
                i += 2
                continue
            if char == '"':
                self._closed = True
                i += 1
                break
            out.append(char)
            i += 1
        self._pos = i
        chunk = "".join(out)
        self.emitted += len(chunk)
        return chunk

    def _find_start(self) -> bool:
        match = re.search(r'"answer"\s*:\s*"', self.buffer)
        if match is None:
            return False
        self._inside = True
        self._pos = match.end()
        return True


def _unicode_escape(buf: str, i: int) -> tuple[str, int]:
    """`\\uXXXX` с позиции i: символ и длина escape; (\"\", 0) — не дописан.
    Суррогатная пара склеивается в один символ, как это делает json."""
    if i + 6 > len(buf):
        return "", 0
    try:
        code = int(buf[i + 2 : i + 6], 16)
    except ValueError:
        return "", 6
    if 0xD800 <= code < 0xDC00:
        if i + 12 > len(buf):
            return "", 0
        if buf[i + 6 : i + 8] == "\\u":
            try:
                low = int(buf[i + 8 : i + 12], 16)
            except ValueError:
                low = 0
            if 0xDC00 <= low < 0xE000:
                return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)), 12
    return chr(code), 6


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
