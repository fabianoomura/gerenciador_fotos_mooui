#!/usr/bin/env bash
set -euo pipefail

: "${CATALOGO_PROJECT_DIR:?Defina CATALOGO_PROJECT_DIR}"
PYTHON="${CATALOGO_PYTHON:-python3}"
DB="${CATALOGO_DB:-catalog.db}"
cd "$CATALOGO_PROJECT_DIR"
exec "$PYTHON" scripts/process_visual.py \
  --db "$DB" --batch-size "${CATALOGO_BATCH_SIZE:-32}"
