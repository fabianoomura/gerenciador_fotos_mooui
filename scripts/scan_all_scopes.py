"""Indexa cada pasta da raiz em transacoes independentes e retomaveis."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.indexer import IndexResult, indexar_metadados  # noqa: E402
from catalogo.parser import normalizar_segmento  # noqa: E402
from catalogo.scanner import validar_mount_readonly  # noqa: E402


def _ordem(path: Path) -> tuple[int, int | str]:
    nome = normalizar_segmento(path.name)
    ano = re.match(r"^(20\d{2})", nome)
    if ano:
        return (0, -int(ano.group(1)))
    return (1, nome)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raiz", type=Path)
    parser.add_argument("--db", type=Path, default=Path("catalogo.db"))
    parser.add_argument("--skip", action="append", default=[])
    args = parser.parse_args()

    validar_mount_readonly(args.raiz)
    ignorar = {normalizar_segmento(nome) for nome in args.skip}
    escopos = sorted(
        [path for path in args.raiz.iterdir() if path.is_dir()],
        key=_ordem,
    )
    totais = IndexResult()
    inicio_geral = time.time()
    executados = 0
    for numero, escopo in enumerate(escopos, 1):
        if normalizar_segmento(escopo.name) in ignorar:
            print(f"SKIP [{numero}/{len(escopos)}] {escopo.name}", flush=True)
            continue
        inicio = time.time()
        print(f"INICIO [{numero}/{len(escopos)}] {escopo.name}", flush=True)
        resumo = indexar_metadados(args.db, escopo)
        executados += 1
        for campo in ("novos", "alterados", "removidos", "ignorados_nao_imagem", "erros"):
            setattr(totais, campo, getattr(totais, campo) + getattr(resumo, campo))
        print(
            f"FIM {escopo.name} novos={resumo.novos} alterados={resumo.alterados} "
            f"removidos={resumo.removidos} ignorados={resumo.ignorados_nao_imagem} "
            f"erros={resumo.erros} segundos={time.time() - inicio:.1f}",
            flush=True,
        )

    print("INICIO arquivos soltos da raiz", flush=True)
    raiz_resultado = indexar_metadados(args.db, args.raiz, recursivo=False)
    for campo in ("novos", "alterados", "removidos", "ignorados_nao_imagem", "erros"):
        setattr(totais, campo, getattr(totais, campo) + getattr(raiz_resultado, campo))
    print(
        f"FINAL escopos={executados} novos={totais.novos} alterados={totais.alterados} "
        f"removidos={totais.removidos} ignorados={totais.ignorados_nao_imagem} "
        f"erros={totais.erros} segundos={time.time() - inicio_geral:.1f}",
        flush=True,
    )
    return 0 if totais.erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
