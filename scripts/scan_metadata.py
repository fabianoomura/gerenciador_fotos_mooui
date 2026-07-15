"""Executa a indexacao read-only de metadados de um escopo do acervo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.indexer import indexar_metadados  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("escopo", type=Path, help="Pasta do share a varrer (deve estar em CIFS ro)")
    parser.add_argument("--db", type=Path, default=Path("catalogo.db"))
    parser.add_argument(
        "--reprocessar",
        action="store_true",
        help="Reaplica o parser mesmo quando mtime/tamanho nao mudaram",
    )
    parser.add_argument(
        "--somente-raiz",
        action="store_true",
        help="Indexa apenas arquivos diretamente no escopo, sem entrar em subpastas",
    )
    args = parser.parse_args()

    resumo = indexar_metadados(
        args.db,
        args.escopo,
        reprocessar=args.reprocessar,
        recursivo=not args.somente_raiz,
    )
    print(f"novos={resumo.novos}")
    print(f"alterados={resumo.alterados}")
    print(f"removidos={resumo.removidos}")
    print(f"ignorados_nao_imagem={resumo.ignorados_nao_imagem}")
    print(f"erros={resumo.erros}")
    return 0 if resumo.erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
