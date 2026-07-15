"""Cria/atualiza catalogo.db aplicando schema.sql + seeds.sql.

Uso:
    python scripts/init_db.py [caminho/para/catalogo.db]

Sem argumento, usa ./catalogo.db no diretorio corrente. Idempotente.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite rodar sem instalar o pacote (dev inicial).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.db import bootstrap, connect  # noqa: E402


def main(argv: list[str]) -> int:
    db_path = Path(argv[1]) if len(argv) > 1 else Path("catalogo.db")
    bootstrap(db_path)

    conn = connect(db_path)
    try:
        n_tipo = conn.execute("SELECT COUNT(*) FROM vocab_tipo").fetchone()[0]
        n_config = conn.execute("SELECT COUNT(*) FROM config").fetchone()[0]
        modelo = conn.execute(
            "SELECT valor FROM config WHERE chave = 'modelo_embedding'"
        ).fetchone()
        share = conn.execute("SELECT valor FROM config WHERE chave = 'share_path'").fetchone()
    finally:
        conn.close()

    print(f"OK -> {db_path.resolve()}")
    print(f"  vocab_tipo: {n_tipo} termos")
    print(f"  config:     {n_config} chaves")
    print(f"  modelo:     {modelo['valor'] if modelo else '(nao definido)'}")
    print(f"  share:      {share['valor'] if share else '(nao definido)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
