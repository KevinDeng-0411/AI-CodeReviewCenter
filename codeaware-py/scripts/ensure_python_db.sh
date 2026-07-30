#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$repo_root"

db_name="ai_center_py"
db_owner="aicenter"
compose_args=(-f "$repo_root/docker-compose.yml")
if [[ -n "${CODEAWARE_COMPOSE_PROJECT:-}" ]]; then
  compose_args=(-p "$CODEAWARE_COMPOSE_PROJECT" "${compose_args[@]}")
fi

docker compose "${compose_args[@]}" up -d postgres

postgres_ready=false
for ((i = 0; i < 60; i++)); do
  if docker compose "${compose_args[@]}" exec -T postgres \
    pg_isready -U "$db_owner" -d postgres >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 1
done
if [[ "$postgres_ready" != "true" ]]; then
  echo "[ensure-python-db] PostgreSQL did not become ready" >&2
  exit 1
fi

current_owner="$(
  docker compose "${compose_args[@]}" exec -T postgres \
    psql -X -U "$db_owner" -d postgres -Atqc \
    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$db_name'"
)"

if [[ -z "$current_owner" ]]; then
  echo "[ensure-python-db] creating $db_name owner=$db_owner"
  if ! docker compose "${compose_args[@]}" exec -T postgres \
    createdb -U "$db_owner" -O "$db_owner" "$db_name"; then
    current_owner="$(
      docker compose "${compose_args[@]}" exec -T postgres \
        psql -X -U "$db_owner" -d postgres -Atqc \
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$db_name'"
    )"
    [[ "$current_owner" == "$db_owner" ]] || {
      echo "[ensure-python-db] create failed and database is not owned by $db_owner" >&2
      exit 1
    }
  fi
else
  echo "[ensure-python-db] $db_name already exists owner=$current_owner"
fi

current_owner="$(
  docker compose "${compose_args[@]}" exec -T postgres \
    psql -X -U "$db_owner" -d postgres -Atqc \
    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$db_name'"
)"
if [[ "$current_owner" != "$db_owner" ]]; then
  echo "[ensure-python-db] refusing to alter owner: expected=$db_owner actual=$current_owner" >&2
  exit 1
fi

echo "[ensure-python-db] ready database=$db_name owner=$db_owner"
