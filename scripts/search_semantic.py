"""CLI simples para validar busca semantica em PT-BR."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.search import buscar_semantica  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("texto")
    parser.add_argument("--db", type=Path, default=Path("catalogo.db"))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    for item in buscar_semantica(args.db, args.texto, limit=args.limit):
        print(f"{item['distancia']:.4f}\t{item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
