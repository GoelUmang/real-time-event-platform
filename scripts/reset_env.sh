#!/usr/bin/env bash
set -euo pipefail
echo "Tearing down environment..."
(cd docker && docker compose down -v --remove-orphans)
echo "Bringing environment back up..."
(cd docker && docker compose up -d --wait)
echo "Environment reset complete."
