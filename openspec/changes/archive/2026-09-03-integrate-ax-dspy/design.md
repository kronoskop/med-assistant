## Context

См. `proposal.md` — зачем нужен Ax. Поведение — в delta specs `ax-programs`, `llm-gateway`, `chat`.

Сейчас `LLMClient` в `app/llm.py` держит `AsyncOpenAI` на `LMSTUDIO_BASE_URL`, клеит `SYSTEM_PROMPT` первым сообщением и вызывает `chat.completions.create` (sync и SSE). HTTP-контракт (`POST /api/v1/chat`, коды `llm_*`, `disclaimer`) менять нельзя. Только локальная MedGemma в LM Studio.

## Goals / Non-Goals

**Goals:**

- Заменить прямой OpenAI-клиент в приложении на Python-пакет `axllm`.
- Один серверный `ax()`-программа для чата; провайдер смотрит только в LM Studio.
- Сохранить адаптер `LLMClient` (или эквивалент) для роутера: те же `complete` / `start_chat_stream` / `ping`.
- Тесты без живой модели.

**Non-Goals:**

- GEPA / `optimize()`, агенты, MCP, tools, playbooks.
- Смена JSON/SSE контракта API.
- TypeScript `@ax-llm/ax`.
- Облачные профили `ai("openai")` без кастомного base URL.

## Decisions

### 1. Пакет `axllm`, не `@ax-llm/ax`

Бэкенд на Python 3.12. Ax документирует Python как `pip install axllm`, `from axllm import ai, ax, OpenAICompatibleClient`.

Альтернатива: поднимать Node-сервис с `@ax-llm/ax` — лишний процесс и дублирование конфига LM Studio.

### 2. Провайдер: `OpenAICompatibleClient` на существующие env

```python
OpenAICompatibleClient(
    api_key=settings.lmstudio_api_key,
    model=settings.lmstudio_model,
    base_url=settings.lmstudio_base_url,
    model_config={"temperature": 0.2},
)
```

`ai("openai", ...)` по умолчанию целится в облако — для этого проекта опасно. Явный compatible-клиент с `base_url` совпадает с текущим шлюзом.

Новые переменные окружения не добавляем. Таймаут: если клиент Ax принимает timeout/transport — прокинуть `LMSTUDIO_TIMEOUT_SECONDS`; иначе обернуть транспорт (`httpx`) с тем же таймаутом.

Альтернатива: оставить `openai.AsyncOpenAI` и звать Ax только для сборки промпта — тогда DSPy-слой фальшивый.

### 3. Одна сигнатура чата, история как вход

Свободный многоходовый чат не совпадает 1:1 с `question -> answer`. Программа:

- инструкция / description = нынешний смысл `SYSTEM_PROMPT` (роль, не диагноз, без отделения);
- вход: сериализованная история `user`/`assistant` из запроса (и при необходимости отдельно последнее сообщение пользователя);
- выход: текст ответа ассистента.

`prompt.py` остаётся источником формулировки роли и отдаёт её в опции сигнатуры, а не в `messages[0]` сырого OpenAI-запроса.

Альтернатива: гнать сырой messages-массив мимо сигнатуры — теряется смысл Ax.

### 4. `LLMClient` — адаптер над Ax, роутер не знает про сигнатуры

Роутер по-прежнему зовёт `complete` / `start_chat_stream`. Внутри:

- нестрим: `program.forward(llm, inputs)` → поле ответа;
- стрим: `streamingForward` (или эквивалент в `axllm`) → чанки текста в существующие SSE-события.

Ax Python в примерах синхронный. FastAPI — async: вызовы Ax оборачивать в `asyncio.to_thread`, пока у пакета нет нативного async. Не блокировать event loop долгим `forward` в корутине.

`ping` / `GET /ready`: не прогонять программу. Либо тонкий HTTP `GET {base}/models` через `httpx` (как сейчас смысл ready), либо метод провайдера Ax, если он есть и не генерирует чат.

### 5. Убрать прямой импорт `openai` из приложения

Прикладной код не вызывает `AsyncOpenAI`. Если `axllm` тянет `openai` транзитивно — это зависимость пакета, не API приложения. Маппинг ошибок (503 / 504 / 502) сохраняем: ловить сетевые/HTTP исключения Ax и `httpx` и переводить в `AppError` с теми же `code`.

Тесты, которые сейчас разбирают JSON `chat.completions` (`messages[0].role == system`), переписать: мок транспорта на base URL LM Studio + проверка, что программа вызвана с историей и что облачный хост не фигурирует. Контракт HTTP-тестов чата не ломаем.

### 6. Structured output vs свободный чат

Ax по умолчанию тянет JSON-схему выхода. MedGemma 4B может плохо держать строгий `json_schema`. Если прогон ломается на разборе — ослабить выход до одной строки ответа (минимальная сигнатура) и оставить валидацию «непустой текст», без лишних полей вроде `confidence`. Это совместимо со spec: наружу по-прежнему `message.content`.

Альтернатива: сразу требовать JSON-объект с несколькими полями — риск 502 на живой модели.

## Risks / Trade-offs

- [Ax сформирует другой wire-формат, чем нынешний messages+system] → приемлемо по delta `chat`; тесты больше не фиксируют сырой OpenAI body, только URL/модель и выход API.
- [Синхронный `axllm` заблокирует event loop] → `asyncio.to_thread` (или async API, если появится).
- [Structured output MedGemma не парсится] → узкая сигнатура `-> answer:string`; ошибка разбора → `llm_error`, не 200 с мусором.
- [Стрим Ax отдаёт не чистый текст поля, а служебные дельты] → в SSE уходит только инкремент текста ответа; служебные события отбрасываются.
- [Случайно сконфигурировать облачный `ai("openai")`] → только `OpenAICompatibleClient` + существующий `LMSTUDIO_BASE_URL`; тесты проверяют, что запрос не идёт на `api.openai.com`.
- [Версия `axllm` на PyPI может разъехаться с докой] → зафиксировать нижнюю границу в `pyproject.toml` на первой рабочей версии; смоук импорта и одного forward с моком.

## Migration Plan

На ветке `integrate-ax-dspy`: добавить `axllm`, перевести `LLMClient`, поправить тесты, `uv lock`. Откат — вернуть прямой OpenAI-клиент; HTTP-клиенты не меняются. Живая проверка: LM Studio + прежние `curl` из README.

## Open Questions

- Точные имена методов стрима и таймаута в установленной версии `axllm` — снимаются при первом `uv add` и чтении пакета; на спеки не влияют.
- Нужен ли позже GEPA на справочных примерах — отдельное изменение.
