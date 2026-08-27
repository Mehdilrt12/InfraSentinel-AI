#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-"$project_dir/.env.production"}
backup_dir=${BACKUP_DIR:-"$project_dir/backups"}
compose_mode=${COMPOSE_MODE:-production}

case "$backup_dir" in
  /*) ;;
  *)
    echo "BACKUP_DIR must be an absolute path." >&2
    exit 2
    ;;
esac

if [ "$backup_dir" = "/" ]; then
  echo "BACKUP_DIR cannot be the filesystem root." >&2
  exit 2
fi

if [ ! -f "$env_file" ]; then
  echo "Environment file not found: $env_file" >&2
  exit 2
fi

case "$compose_mode" in
  local|production) ;;
  *)
    echo "COMPOSE_MODE must be local or production." >&2
    exit 2
    ;;
esac

mkdir -p "$backup_dir"
chmod 0700 "$backup_dir"
umask 077

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_path="$backup_dir/infrasentinel-$timestamp.dump"
temporary_path=$(mktemp "$backup_dir/.infrasentinel-$timestamp.XXXXXX")
trap 'rm -f "$temporary_path"' EXIT HUP INT TERM

if [ "$compose_mode" = "local" ]; then
  docker compose \
    --env-file "$env_file" \
    -f "$project_dir/docker-compose.yml" \
    exec -T db sh -eu -c \
    'pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
    > "$temporary_path"
else
  docker compose \
    --env-file "$env_file" \
    -f "$project_dir/docker-compose.yml" \
    -f "$project_dir/docker-compose.prod.yml" \
    exec -T db sh -eu -c \
    'pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
    > "$temporary_path"
fi

test -s "$temporary_path"
mv "$temporary_path" "$final_path"
trap - EXIT HUP INT TERM
sha256sum "$final_path" > "$final_path.sha256"
echo "$final_path"
