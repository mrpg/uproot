#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")"

model_cases="$(mktemp -d)"
trap 'rm -rf "$model_cases"' EXIT
gzip -dc tests/cases/room-cases.jsonl.gz > "$model_cases/room-cases.jsonl"
gzip -dc tests/cases/page-cases.jsonl.gz > "$model_cases/page-cases.jsonl"

export UPROOT_DATABASE=sqlite3 UPROOT_SQLITE3=:memory: UPROOT_MODEL_TESTS=1
export UPROOT_FORMAL_CASES="$model_cases/room-cases.jsonl"
export UPROOT_PAGE_CASES="$model_cases/page-cases.jsonl"
timeout 300s uv run pytest --no-cov tests/test_rooms_model.py::test_refinement "$@"

parallelism="$(nproc)"
seq 0 "$((parallelism - 1))" | xargs -P "$parallelism" -I '{}' bash -c '
    log="$UPROOT_FORMAL_CASES.$1.log"
    export UPROOT_FORMAL_SHARD="$1/$2"
    shift 2
    timeout 1800s uv run --no-sync pytest --no-cov -q \
        tests/test_rooms_model.py::test_admission_cases \
        tests/test_pages_model.py::test_page_cases "$@" > "$log" 2>&1 || {
        cat "$log"
        exit 1
    }
' model-replay '{}' "$parallelism" "$@"
echo "All room and page cases passed across $parallelism shards."
