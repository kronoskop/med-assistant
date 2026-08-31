## Context

Репозиторий пустой (только OpenSpec). Мотивация — в `proposal.md`. Поведение — в `specs/http-api`, `specs/chat`, `specs/llm-gateway`.

Ограничения: только API, без UI и БД; модель уже в LM Studio (OpenAI-совместимый сервер, по умолчанию `http://127.0.0.1:1234/v1`); дизайн должен читаться с первого взгляда.

## Goals / Non-Goals

**Goals:**

- Один маленький Python-пакет: HTTP-слой, промпт, клиент LM Studio.
- Конфиг только из env, понятные дефолты под локальную MedGemma.
- Тесты без живой модели: LM Studio подменяется.

**Non-Goals:**

- Слои «hexagonal / DDD», очереди, кэш, Docker, CI.
- Авторизация, хранение чатов, картинки (хотя MedGemma 1.5 мультимодальная).
- Свой протокол вместо OpenAI chat completions на стороне LM Studio.

## Decisions

### 1. FastAPI + uvicorn

Простой типизированный JSON API, из коробки OpenAPI (`/docs` — для разработчика, не продуктовый UI) и SSE через `StreamingResponse`.

Альтернативы: Flask (меньше удобства для схем и стрима), Django (лишний вес без БД и админки).

### 2. Официальный OpenAI Python-клиент на локальный base URL

LM Studio отдаёт `POST /v1/chat/completions`. Клиент `openai` с `base_url` из настроек и `api_key` из env (дефолт `lm-studio`, LM Studio часто требует непустой ключ). Облачный `api.openai.com` не используется.

Альтернативы: сырой `httpx` (больше кода на стрим и ошибки), `lmstudio` SDK (привязка к вендору, хуже знакомый контракт).

### 3. Плоская структура `app/`

```
app/
  main.py        # FastAPI app, обработчики ошибок
  settings.py    # pydantic-settings
  schemas.py     # запрос/ответ/ошибка
  prompt.py      # системный промпт для медперсонала
  llm.py         # вызов LM Studio + маппинг ошибок
  routers.py     # GET /health, GET /ready, POST /api/v1/chat
tests/
pyproject.toml
.env.example
```

Без вложенных `domain/infrastructure`. Роутер вызывает `llm` напрямую.

### 4. Stateless: история только в теле запроса

Сервер не хранит диалоги. Клиент шлёт полный `messages`. Системный промпт всегда добавляется на сервере первым сообщением.

### 5. SSE, не сырой OpenAI stream снаружи

Наружу: `text/event-stream`. События: `data: {"text": "..."}` и финальное `data: [DONE]` (или `event: done`). Внутри — `stream=True` у клиента OpenAI. Если соединение к LM Studio не устанавливается, стрим не открывается: сразу HTTP 503.

### 6. Дефолтный bind `127.0.0.1`

Авторизации нет (см. spec). Процесс слушает localhost, чтобы API случайно не торчал в сеть. Хост/порт переопределяются env (`APP_HOST`, `APP_PORT`, дефолт порта `8000`).

### 7. Логи без текста сообщений

В лог: метод, путь, статус, latency, код ошибки. Тело чата и промпт не пишем — в медицинском контексте это потенциальные ПДн/врачебная тайна.

### 8. Тесты: pytest + httpx ASGI, мок LLM

Юнит-тесты роутеров с подменой `llm`. Отдельный тест клиента с `httpx.MockTransport` или respx. Живая MedGemma в CI не нужна; опциональный ручной прогон против LM Studio документируется в README.

### 9. Зависимости и запуск

Python 3.12+, `pyproject.toml` (зависимости: `fastapi`, `uvicorn`, `openai`, `pydantic-settings`, `httpx`). Запуск: `uvicorn app.main:app --host 127.0.0.1 --port 8000`. Менеджер пакетов: `uv` если есть, иначе `pip`.

Переменные (`.env.example`):

| Переменная | Дефолт |
|---|---|
| `APP_HOST` | `127.0.0.1` |
| `APP_PORT` | `8000` |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` |
| `LMSTUDIO_MODEL` | `med-gemma-1.5-4b` |
| `LMSTUDIO_API_KEY` | `lm-studio` |
| `LMSTUDIO_TIMEOUT_SECONDS` | `120` |

`GET /ready`: `GET {base}/models` (список моделей, без генерации).

Температура апстрима: `0.2` (стабильнее для клинической справки). Не торчим в публичном API.

## Risks / Trade-offs

- [Идентификатор модели в LM Studio может отличаться от `med-gemma-1.5-4b`] → в README явно: скопировать id из LM Studio в `LMSTUDIO_MODEL`.
- [Нет auth: утечка, если сменить bind на `0.0.0.0`] → дефолт localhost; в README предупреждение.
- [ПДн в запросах к локальной модели] → не логируем контент; данные не уходят в облако. Юридический контур (согласие, хранение на клиенте) — вне этого изменения.
- [4B-модель ошибается] → системный промпт + `disclaimer` в JSON; это поддержка врача, не заключение.
- [Долгая генерация / обрыв SSE] → таймаут 120 с; клиент должен уметь оборвать HTTP.
- [OpenAPI `/docs` могут счесть UI] → это служебная схема для разработчика, не продукт для медперсонала; HTML-приложения нет.

## Migration Plan

Первый запуск: установить зависимости, поднять LM Studio с MedGemma, `uvicorn`, проверить `GET /health` и `POST /api/v1/chat`. Откат: остановить процесс, кода в проде ещё нет.

## Open Questions

- Точное имя GGUF/модели в UI LM Studio у разработчика — решается env, на спецификацию не влияет.
- Нужен ли Docker позже — не блокирует этот срез.
