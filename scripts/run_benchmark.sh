#!/usr/bin/env bash
set -euo pipefail

echo "Starting Docker Compose stack (3 workers)..."
(cd docker && docker compose up -d --build --scale worker=4 --wait)

echo "Waiting for API readiness..."
until curl -sf http://localhost:8000/docs > /dev/null; do sleep 1; done
echo "API ready."

echo "Running benchmark..."
python -m load_testing.benchmark_runner

echo ""
echo "Prometheus snapshot — events_processed_total:"
curl -s "http://localhost:9090/api/v1/query?query=events_processed_total" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  [print(r['metric'], r['value']) for r in d['data']['result']]"
