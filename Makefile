.PHONY: install run test bench bench-retrieval

UVICORN_HOST ?= 127.0.0.1
UVICORN_PORT ?= 8000

install:
	uv sync --extra dev

run:
	uv run uvicorn app.main:app --host $(UVICORN_HOST) --port $(UVICORN_PORT)

test:
	uv run pytest -q

# Замер на проверочном наборе: нужен запущенный `make run` и LM Studio.
BENCH_URL ?= http://$(UVICORN_HOST):$(UVICORN_PORT)
bench:
	uv run python tools/bench.py chat --url $(BENCH_URL) $(ARGS)

# Только отбор фрагментов, без генерации: нужен индекс и модель эмбеддингов.
bench-retrieval:
	uv run python tools/bench.py retrieval $(ARGS)
