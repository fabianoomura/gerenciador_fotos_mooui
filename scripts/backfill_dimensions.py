"""Backfill de largura/altura/orientacao lendo apenas cabecalhos com Pillow.

Retomavel (processa somente largura IS NULL) e seguro com a API no ar:
o banco fica em WAL, os commits sao curtos e nada alem das colunas novas
e' alterado. Tambem preenche possui_pessoa quando ha evidencia no proprio
registro (pessoa/pessoa_tipo), sem nenhuma inferencia por IA.

Uso (produção, dentro do WSL):
    python scripts/backfill_dimensions.py --db /caminho/catalogo.db --workers 16
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from catalogo.indexer import calcular_orientacao, ler_dimensoes  # noqa: E402


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--batch", type=int, default=500, help="linhas por transacao")
    parser.add_argument("--limit", type=int, help="maximo de imagens nesta execucao")
    return parser.parse_args()


def conectar(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def preencher_possui_pessoa(conn: sqlite3.Connection) -> int:
    """Evidencia direta no registro; NULL continua significando desconhecido."""

    cursor = conn.execute(
        """
        UPDATE imagens SET possui_pessoa = 1
        WHERE possui_pessoa IS NULL
          AND (pessoa IS NOT NULL OR pessoa_tipo IS NOT NULL)
        """
    )
    conn.commit()
    return cursor.rowcount


def backfill_dimensoes(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[int, int]:
    pendentes = conn.execute(
        "SELECT COUNT(*) FROM imagens WHERE largura IS NULL AND status != 'removido'"
    ).fetchone()[0]
    print(f"pendentes: {pendentes}", flush=True)

    processadas = 0
    erros = 0
    cursor_id = 0
    inicio = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while True:
            if args.limit and processadas >= args.limit:
                break
            lote = conn.execute(
                """
                SELECT id, path FROM imagens
                WHERE largura IS NULL AND status != 'removido' AND id > ?
                ORDER BY id LIMIT ?
                """,
                (cursor_id, args.batch),
            ).fetchall()
            if not lote:
                break
            cursor_id = lote[-1]["id"]
            dimensoes = list(pool.map(lambda r: ler_dimensoes(Path(r["path"])), lote))
            atualizacoes = []
            for row, (largura, altura) in zip(lote, dimensoes, strict=True):
                if largura is None:
                    erros += 1
                    print(f"erro ao ler: {row['path']}", file=sys.stderr, flush=True)
                    continue
                atualizacoes.append(
                    (largura, altura, calcular_orientacao(largura, altura), row["id"])
                )
            conn.executemany(
                "UPDATE imagens SET largura=?, altura=?, orientacao=? WHERE id=?",
                atualizacoes,
            )
            conn.commit()
            processadas += len(lote)
            ritmo = processadas / max(time.time() - inicio, 1e-6)
            restante = (pendentes - processadas) / ritmo if ritmo else 0
            print(
                f"{processadas}/{pendentes} ({ritmo:.0f} img/s, "
                f"~{restante / 60:.0f} min restantes, erros={erros})",
                flush=True,
            )
    return processadas, erros


def main() -> None:
    args = argumentos()
    conn = conectar(args.db)
    try:
        com_pessoa = preencher_possui_pessoa(conn)
        print(f"possui_pessoa preenchido em {com_pessoa} registros", flush=True)
        processadas, erros = backfill_dimensoes(conn, args)
        print(f"concluido: {processadas} processadas, {erros} erros", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
