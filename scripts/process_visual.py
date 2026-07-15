"""CLI do processamento de paleta e embeddings CLIP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.visual import processar_visuais  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("catalogo.db"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int)
    args = parser.parse_args()

    def progresso(parcial, total: int) -> None:
        concluidas = parcial.processadas + parcial.erros
        print(
            f"progresso={concluidas}/{total} processadas={parcial.processadas} "
            f"erros={parcial.erros}",
            flush=True,
        )

    resumo = processar_visuais(
        args.db,
        limit=args.limit,
        batch_size=args.batch_size,
        progress_callback=progresso,
    )
    print(f"processadas={resumo.processadas}")
    print(f"erros={resumo.erros}")
    return 0 if resumo.erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
