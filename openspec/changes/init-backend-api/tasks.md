## 1. Каркас проекта

- [ ] 1.1 Добавить `pyproject.toml` (Python ≥3.12, пакет `app`, зависимости `fastapi`, `uvicorn`, `openai`, `pydantic-settings`, `httpx`; dev: `pytest`, `httpx`) и проверить, что `pip install -e ".[dev]"` или `uv sync` завершается без ошибки
- [ ] 1.2 Создать пустые модули `app/main.py`, `app/settings.py`, `app/schemas.py`, `app/prompt.py`, `app/llm.py`, `app/routers.py` и каталог `tests/`; проверить, что дерево совпадает с `design.md`
- [ ] 1.3 Добавить `.env.example` с `APP_HOST`, `APP_PORT`, `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`, `LMSTUDIO_API_KEY`, `LMSTUDIO_TIMEOUT_SECONDS` и проверить, что имена и дефолты совпадают со spec `http-api` / `llm-gateway`
- [ ] 1.4 Добавить `.gitignore` для `.venv`, `__pycache__`, `.env` и проверить, что секреты из `.env` не попадут в git
- [ ] 1.5 Добавить makefile для автоматизации запуска проекта



## 2. HTTP-сервис и конфиг

- [ ] 2.1 Реализовать `settings.py` (pydantic-settings): дефолты `127.0.0.1:8000`, `http://127.0.0.1:1234/v1`, модель `med-gemma-1.5-4b`, таймаут 120 с; проверить тестом, что без env подставляются дефолты и что `LMSTUDIO_*` переопределяются
- [ ] 2.2 Собрать FastAPI в `main.py` (JSON-only, единый обработчик ошибок `{code, message}` для 404 и невалидного JSON) и проверить `GET /health` → 200 `{"status":"ok"}` и неизвестный путь → 404 JSON
- [ ] 2.3 Добавить access-лог без тел запросов (метод, путь, статус, latency) и проверить, что в логе нет текста сообщений чата



## 3. Шлюз LM Studio

- [ ] 3.1 Реализовать клиент в `llm.py` на `openai.OpenAI`/`AsyncOpenAI` с `base_url` и `api_key` из настроек (не облачный OpenAI) и проверить юнит-тестом, что в запрос уходит `model` из настроек
- [ ] 3.2 Замапить ошибки апстрима: connection error → `llm_unavailable` (503), timeout → `llm_timeout` (504), HTTP/модель не найдена → `llm_error` (502); проверить тестами с моком транспорта
- [ ] 3.3 Реализовать `GET /ready` через `GET {base}/models` без генерации и проверить: апстрим отвечает → 200 `"ready"`, отказ соединения → 503 `"not_ready"` с `code`



## 4. Чат

- [ ] 4.1 Описать схемы `POST /api/v1/chat`: `messages` (role `user`|`assistant`, непустой `content` string), `stream` bool default false; отклонять `role: system` и не-строковый content (400/422 JSON); проверить тестами валидации
- [ ] 4.2 Вынести в `prompt.py` системный промпт для медперсонала (поддержка решения, не диагноз, без специализации по отделению) и константу `disclaimer`; проверить, что промпт непустой и содержит оговорку
- [ ] 4.3 Собрать апстрим-сообщения: серверный system первым + клиентский `messages`; не сохранять историю; проверить тестом, что повторный запрос без прошлых реплик не подмешивает старый контекст
- [ ] 4.4 Реализовать нестриминговый `POST /api/v1/chat`: HTTP 200, `message.role=assistant`, непустой `message.content`, поле `disclaimer`; проверить тестом с моком LLM
- [ ] 4.5 При недоступном LM Studio нестриминговый чат возвращает 503 `llm_unavailable` (не 200); проверить тестом



## 5. Поток SSE

- [ ] 5.1 При `"stream": true` отдавать `text/event-stream`: события `data: {"text":"..."}` и терминальное `data: [DONE]`; проверить тестом, что приходят фрагменты и done
- [ ] 5.2 Если к LM Studio нельзя подключиться до открытия стрима — HTTP 503 JSON, а не «успешный» SSE; проверить тестом



## 6. Документация

- [ ] 6.1 Обновить корневой `README.md`: запуск LM Studio с MedGemma, копирование id модели в `LMSTUDIO_MODEL`, `uvicorn`, примеры `curl` для `/health`, `/ready`, `/api/v1/chat`; предупреждение: bind только localhost, нет auth, данные не логируются и не уходят в облако. Проверить, что команды из README копируются без правок