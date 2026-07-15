#!/usr/bin/env bash
set -euo pipefail

: "${CATALOGO_PROJECT_DIR:?Defina CATALOGO_PROJECT_DIR}"
: "${CATALOGO_PHOTO_ROOT:?Defina CATALOGO_PHOTO_ROOT}"
PYTHON="${CATALOGO_PYTHON:-python3}"
DB="${CATALOGO_DB:-catalog.db}"
cd "$CATALOGO_PROJECT_DIR"

echo "=== METADATA INICIO $(date --iso-8601=seconds) ==="
"$PYTHON" scripts/scan_all_scopes.py "$CATALOGO_PHOTO_ROOT" --db "$DB"
echo "=== METADATA FIM $(date --iso-8601=seconds) ==="

echo "=== CORES COMERCIAIS INICIO $(date --iso-8601=seconds) ==="
"$PYTHON" scripts/reprocess_commercial_colors.py "$DB"
echo "=== CORES COMERCIAIS FIM $(date --iso-8601=seconds) ==="

echo "=== VISUAL INICIO $(date --iso-8601=seconds) ==="
"$PYTHON" scripts/process_visual.py --db "$DB" --batch-size "${CATALOGO_BATCH_SIZE:-32}"
echo "=== VISUAL FIM $(date --iso-8601=seconds) ==="
