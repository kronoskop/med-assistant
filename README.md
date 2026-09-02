# med-assistant

HTTP API ИИ-ассистента для медперсонала. Модель — локальная **MedGemma** (`med-gemma-1.5-4b`) в [LM Studio](https://lmstudio.ai/). Веб-интерфейса нет: только JSON API.

Ассистент — поддержка решения врача, не диагноз. Специализации по отделению нет.

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (или pip)
- LM Studio с загруженной MedGemma и включённым локальным сервером (по умолчанию `http://127.0.0.1:1234`)

## Настройка

1. В LM Studio откройте Developer и запустите сервер.
2. Скопируйте идентификатор загруженной модели (он может отличаться от `med-gemma-1.5-4b`) и запишите в `LMSTUDIO_MODEL`.
3. Скопируйте `.env.example` в `.env` и при необходимости поправьте значения.

```bash
cp .env.example .env
```

| Переменная | Значение по умолчанию |
|---|---|
| `APP_HOST` | `127.0.0.1` |
| `APP_PORT` | `8000` |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` |
| `LMSTUDIO_MODEL` | `med-gemma-1.5-4b` |
| `LMSTUDIO_API_KEY` | `lm-studio` |
| `LMSTUDIO_TIMEOUT_SECONDS` | `120` |

По умолчанию процесс слушает только localhost. Авторизации нет: не выставляйте `APP_HOST=0.0.0.0` в открытую сеть.

Тела чатов не пишутся в лог и не уходят в облачные LLM.

## Запуск

```bash
make install
make run
```

Без make:

```bash
uv sync --extra dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Или pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Проверка, что API живо (без вызова модели):

```bash
curl http://127.0.0.1:8000/health
```

Проверка, что LM Studio отвечает:

```bash
curl http://127.0.0.1:8000/ready
```

Чат без потока:

```bash
curl http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Кратко напомни критерии оценки обезвоживания у ребёнка"}]}'
```

Поток SSE:

```bash
curl -N http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"stream":true,"messages":[{"role":"user","content":"Кратко напомни критерии оценки обезвоживания у ребёнка"}]}'
```

Историю диалога сервер не хранит: каждый запрос должен содержать нужный список `messages`.

## Тесты

```bash
make test
```

Живая MedGemma для тестов не нужна: LM Studio подменяется.

Служебная схема OpenAPI: `http://127.0.0.1:8000/docs` (для разработчика, не продуктовый UI).
