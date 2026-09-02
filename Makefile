.PHONY: install run test

UVICORN_HOST ?= 127.0.0.1
UVICORN_PORT ?= 8000

install:
	uv sync --extra dev

run:
	uv run uvicorn app.main:app --host $(UVICORN_HOST) --port $(UVICORN_PORT)

test:
	uv run pytest -q
