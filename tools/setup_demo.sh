#!/usr/bin/env bash
# Поднять демо на Mac одной командой: зависимости, корпус, индекс, сервер, Tailscale.
#
#   ./tools/setup_demo.sh          # всё по порядку; повторный запуск быстрый
#   ./tools/setup_demo.sh stop     # остановить сервер демо
#
# Что нужно заранее: LM Studio с загруженными MedGemma и
# text-embedding-multilingual-e5-small. Tailscale — по желанию: без него
# интерфейс доступен только на этой машине.
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${APP_PORT:-8000}"
LMS_URL="${LMSTUDIO_BASE_URL:-http://127.0.0.1:1234/v1}"
PID_FILE=".demo.pid"
LOG_FILE="demo.log"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mОшибка:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "stop" ]]; then
  if [[ -f "$PID_FILE" ]] && kill "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Сервер демо остановлен."
  else
    echo "Сервер демо не запущен."
  fi
  rm -f "$PID_FILE"
  exit 0
fi

say "1/6 Инструменты"
if ! command -v uv >/dev/null; then
  echo "uv не найден — ставлю (https://docs.astral.sh/uv/)."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

LMS="$(command -v lms || true)"
[[ -z "$LMS" && -x "$HOME/.lmstudio/bin/lms" ]] && LMS="$HOME/.lmstudio/bin/lms"

say "2/6 LM Studio"
if ! curl -fsS -m 3 "$LMS_URL/models" >/dev/null 2>&1; then
  if [[ -n "$LMS" ]]; then
    echo "Сервер LM Studio не отвечает — запускаю через lms."
    "$LMS" server start
    sleep 3
  fi
  curl -fsS -m 5 "$LMS_URL/models" >/dev/null 2>&1 \
    || fail "LM Studio не отвечает на $LMS_URL. Откройте LM Studio → Developer → Start Server."
fi
MODELS="$(curl -fsS "$LMS_URL/models" | python3 -c 'import json,sys; print("\n".join(m["id"] for m in json.load(sys.stdin)["data"]))')"
echo "Модели в LM Studio:"; echo "$MODELS" | sed 's/^/  /'
CHAT_MODEL="${LMSTUDIO_MODEL:-$(echo "$MODELS" | grep -iE 'med-?gemma' | head -1 || true)}"
EMBED_MODEL="${EMBEDDING_MODEL:-$(echo "$MODELS" | grep -i 'e5-small' | head -1 || true)}"
[[ -n "$CHAT_MODEL" ]] || fail "MedGemma не найдена в LM Studio. Скачайте её в разделе Discover (лучше MLX-сборку, если есть)."
[[ -n "$EMBED_MODEL" ]] || fail "Модель эмбеддингов не найдена. Скачайте text-embedding-multilingual-e5-small в LM Studio."
echo "Чат: $CHAT_MODEL"
echo "Эмбеддинги: $EMBED_MODEL"

say "3/6 Настройки"
[[ -f .env ]] || cp .env.example .env
set_env() {
  if grep -q "^$1=" .env; then
    python3 - "$1" "$2" <<'PY'
import sys, pathlib
key, value = sys.argv[1], sys.argv[2]
path = pathlib.Path(".env")
lines = [f"{key}={value}" if l.startswith(key + "=") else l for l in path.read_text().splitlines()]
path.write_text("\n".join(lines) + "\n")
PY
  else
    echo "$1=$2" >> .env
  fi
}
set_env LMSTUDIO_MODEL "$CHAT_MODEL"
set_env EMBEDDING_MODEL "$EMBED_MODEL"
echo ".env обновлён."

say "4/6 Зависимости"
uv sync --extra dev -q

say "5/6 Корпус и индекс (первый раз — долго: скачивание и разбор PDF)"
uv run python tools/build_corpus.py

say "6/6 Сервер"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Перезапускаю сервер демо."
  kill "$(cat "$PID_FILE")" || true
  sleep 1
fi
nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
for _ in $(seq 1 30); do
  curl -fsS -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null || fail "Сервер не поднялся, смотрите $LOG_FILE"
READY="$(curl -s "http://127.0.0.1:$PORT/ready" || true)"
echo "Готовность: $READY"

TS="$(command -v tailscale || true)"
[[ -z "$TS" && -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]] && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
if [[ -n "$TS" ]]; then
  "$TS" serve --bg "$PORT" >/dev/null
  HOST="$("$TS" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  say "Демо открыто в сети Tailscale: https://$HOST/ui"
else
  say "Демо открыто на этой машине: http://127.0.0.1:$PORT/ui (Tailscale не найден)"
fi
echo "Журнал сервера: $LOG_FILE · остановить: ./tools/setup_demo.sh stop"
echo "Замер: make bench-retrieval && make bench ARGS=\"--label parallel\""
