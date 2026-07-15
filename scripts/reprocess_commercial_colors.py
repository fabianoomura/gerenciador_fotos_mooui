"""Deriva cores comerciais e de marketing das paletas existentes, sem reler imagens."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.db import bootstrap, connect  # noqa: E402
from catalogo.palette import simplificar_cores  # noqa: E402


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("catalogo.db")
    bootstrap(db_path)
    conn = connect(db_path)
    try:
        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        referencias_marketing = json.loads(config["cores_marketing"])
        rows = conn.execute(
            """
            SELECT id, paleta_json FROM imagens
            WHERE paleta_json IS NOT NULL AND cores_marketing_json IS NULL
            """
        ).fetchall()
        pendentes = []
        for numero, row in enumerate(rows, 1):
            cores_marketing = simplificar_cores(
                json.loads(row["paleta_json"]),
                referencias_marketing,
                max_cores=int(config["cores_marketing_max"]),
                min_proporcao=float(config["cores_marketing_min_proporcao"]),
            )
            pendentes.append((json.dumps(cores_marketing, ensure_ascii=False), row["id"]))
            if numero % 1000 == 0:
                conn.executemany(
                    "UPDATE imagens SET cores_marketing_json=? WHERE id=?",
                    pendentes,
                )
                conn.commit()
                pendentes.clear()
                print(f"progresso={numero}/{len(rows)}", flush=True)
        if pendentes:
            conn.executemany(
                "UPDATE imagens SET cores_marketing_json=? WHERE id=?",
                pendentes,
            )
        conn.commit()
        print(f"processadas={len(rows)}", flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
