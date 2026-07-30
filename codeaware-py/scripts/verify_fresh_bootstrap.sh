#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
run_id="$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
project="codeaware-bootstrap-$run_id"
tmp_dir="$(mktemp -d)"
app_pid=""

free_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

export CODEAWARE_PG_HOST_PORT="$(free_port)"
export CODEAWARE_REDIS_HOST_PORT="$(free_port)"
export CODEAWARE_OLLAMA_HOST_PORT="$(free_port)"
api_port="$(free_port)"
export CODEAWARE_POSTGRES_CONTAINER_NAME="${project}-postgres"
export CODEAWARE_REDIS_CONTAINER_NAME="${project}-redis"
export CODEAWARE_OLLAMA_CONTAINER_NAME="${project}-ollama"

compose() {
  docker compose -p "$project" -f "$repo_root/docker-compose.yml" "$@"
}

development_fingerprint() {
  {
    docker compose -f "$repo_root/docker-compose.yml" ps -a \
      --format '{{.ID}}|{{.Name}}|{{.State}}|{{.Image}}' 2>/dev/null | sort || true
    docker volume inspect \
      ai-center_pgdata ai-center_redisdata ai-center_ollamadata \
      --format '{{.Name}}|{{.Driver}}|{{index .Labels "com.docker.compose.project"}}' \
      2>/dev/null | sort || true
  }
}

development_fingerprint >"$tmp_dir/development-before.json"

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  if [[ -n "$app_pid" ]]; then
    kill "$app_pid" 2>/dev/null
    wait "$app_pid" 2>/dev/null
  fi
  compose down -v --remove-orphans >"$tmp_dir/compose-down.log" 2>&1
  local down_rc=$?
  development_fingerprint >"$tmp_dir/development-after.json"
  if [[ $down_rc -ne 0 ]]; then
    echo "[fresh-bootstrap] cleanup failed project=$project" >&2
    rc=1
  else
    echo "[fresh-bootstrap] exact cleanup complete project=$project"
  fi
  if ! cmp -s "$tmp_dir/development-before.json" "$tmp_dir/development-after.json"; then
    echo "[fresh-bootstrap] development resource fingerprint changed" >&2
    rc=1
  else
    echo "[fresh-bootstrap] development resource fingerprint unchanged"
  fi
  if [[ $rc -ne 0 && -f "$tmp_dir/api.log" ]]; then
    tail -80 "$tmp_dir/api.log" >&2
  fi
  rm -rf "$tmp_dir"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[fresh-bootstrap] project=$project"
echo "[fresh-bootstrap] pg=127.0.0.1:$CODEAWARE_PG_HOST_PORT redis=127.0.0.1:$CODEAWARE_REDIS_HOST_PORT ollama=127.0.0.1:$CODEAWARE_OLLAMA_HOST_PORT api=127.0.0.1:$api_port"

compose up -d --wait --wait-timeout 180

db_rows="$(
  compose exec -T postgres psql -X -U aicenter -d postgres -AtF '|' -c \
    "SELECT datname, pg_get_userbyid(datdba) FROM pg_database WHERE datname IN ('ai_center','ai_center_py') ORDER BY datname"
)"
expected_db_rows=$'ai_center|aicenter\nai_center_py|aicenter'
if [[ "$db_rows" != "$expected_db_rows" ]]; then
  echo "[fresh-bootstrap] unexpected databases/owners:" >&2
  echo "$db_rows" >&2
  exit 1
fi
echo "[fresh-bootstrap] databases ready: ai_center owner=aicenter, ai_center_py owner=aicenter"
CODEAWARE_COMPOSE_PROJECT="$project" "$app_root/scripts/ensure_python_db.sh"
echo "[fresh-bootstrap] existing-volume database helper is idempotent"

export PG_HOST="127.0.0.1"
export PG_PORT="$CODEAWARE_PG_HOST_PORT"
export PG_USER="aicenter"
export PG_PASSWORD="aicenter123"
export PG_DB="ai_center_py"
export REDIS_HOST="127.0.0.1"
export REDIS_PORT="$CODEAWARE_REDIS_HOST_PORT"
export REDIS_DB="0"
export OLLAMA_BASE_URL="http://127.0.0.1:$CODEAWARE_OLLAMA_HOST_PORT"

(cd "$app_root" && uv run alembic upgrade head)
alembic_current="$(cd "$app_root" && uv run alembic current)"
if [[ "$alembic_current" != *"(head)"* ]]; then
  echo "[fresh-bootstrap] Alembic current is not head: $alembic_current" >&2
  exit 1
fi
echo "[fresh-bootstrap] Alembic current=$alembic_current"

prompt_rows="$(
  compose exec -T postgres psql -X -U aicenter -d ai_center_py -At -c \
    "SELECT type || '=' || count(*) FROM prompt_templates WHERE is_active GROUP BY type ORDER BY type"
)"
expected_prompt_rows=$'AI_README=1\nCHAT=1\nCODE_REVIEW=1\nUNIT_TEST=1'
if [[ "$prompt_rows" != "$expected_prompt_rows" ]]; then
  echo "[fresh-bootstrap] active prompt seed mismatch:" >&2
  echo "$prompt_rows" >&2
  exit 1
fi
echo "[fresh-bootstrap] active prompts: AI_README=1 CHAT=1 CODE_REVIEW=1 UNIT_TEST=1"

(
  cd "$app_root"
  CODEAWARE_TESTING=1 uv run uvicorn app.main:app \
    --host 127.0.0.1 --port "$api_port"
) >"$tmp_dir/api.log" 2>&1 &
app_pid=$!

wait_http_200() {
  local url=$1
  local attempts=${2:-60}
  local status=""
  for ((i = 0; i < attempts; i++)); do
    status="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    [[ "$status" == "200" ]] && return 0
    sleep 1
  done
  echo "[fresh-bootstrap] endpoint did not become ready: $url status=$status" >&2
  return 1
}

wait_http_200 "http://127.0.0.1:$api_port/health"
wait_http_200 "http://127.0.0.1:$api_port/health/live"
wait_http_200 "http://127.0.0.1:$api_port/health/ready"
wait_http_200 "http://127.0.0.1:$api_port/docs"
echo "[fresh-bootstrap] HTTP /health=200 /health/live=200 /health/ready=200 /docs=200"

compose stop redis
live_status="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$api_port/health/live")"
ready_status="$(curl -sS -o "$tmp_dir/readiness-down.json" -w '%{http_code}' "http://127.0.0.1:$api_port/health/ready")"
if [[ "$live_status" != "200" || "$ready_status" != "503" ]]; then
  echo "[fresh-bootstrap] readiness degradation mismatch live=$live_status ready=$ready_status" >&2
  exit 1
fi
python3 -c \
  'import json,sys; d=json.load(open(sys.argv[1])); assert d["data"]["checks"]["redis"] == "down"' \
  "$tmp_dir/readiness-down.json"
echo "[fresh-bootstrap] Redis stopped: liveness=200 readiness=503 redis=down"

compose start redis
for ((i = 0; i < 60; i++)); do
  if compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 1
done
wait_http_200 "http://127.0.0.1:$api_port/health/ready"
echo "[fresh-bootstrap] Redis restored: readiness=200"

(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py \
    tests/test_safeguard.py \
    tests/test_safe_runner.py \
    tests/test_validator.py \
    tests/test_health.py \
    tests/test_migration.py \
    -q
)
echo "[fresh-bootstrap] guard allow/refuse, validator, health, migration roundtrip passed"
