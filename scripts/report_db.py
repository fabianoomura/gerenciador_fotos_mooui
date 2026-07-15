"""Relatorio compacto de auditoria do catalogo SQLite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.db import connect  # noqa: E402


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("catalogo.db")
    conn = connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM imagens").fetchone()[0]
        status = [
            tuple(row)
            for row in conn.execute(
                "SELECT status, COUNT(*) FROM imagens GROUP BY status ORDER BY status"
            ).fetchall()
        ]
        tipos = [
            tuple(row)
            for row in conn.execute(
                """
            SELECT COALESCE(tipo, '(null)'), COUNT(*)
            FROM imagens GROUP BY tipo ORDER BY COUNT(*) DESC
            """
            ).fetchall()
        ]
        proxies = conn.execute(
            "SELECT COUNT(*) FROM imagens WHERE reduzida_path IS NOT NULL"
        ).fetchone()[0]
        reduzidas_registros = conn.execute(
            "SELECT COUNT(*) FROM imagens WHERE instr(lower(path), '/reduzidas/') > 0"
        ).fetchone()[0]
        pendentes = [
            tuple(row)
            for row in conn.execute(
                """
            SELECT segmento_pendente, COUNT(*) AS n
            FROM nao_classificados
            GROUP BY segmento_pendente ORDER BY n DESC LIMIT 10
            """
            ).fetchall()
        ]
        amostras = {}
        for segmento, _ in pendentes[:5]:
            amostras[segmento] = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT i.path
                    FROM imagens i
                    JOIN nao_classificados n ON n.imagem_id = i.id
                    WHERE n.segmento_pendente = ?
                    LIMIT 3
                    """,
                    (segmento,),
                )
            ]
        runs = [
            tuple(row)
            for row in conn.execute(
                """
            SELECT novos, alterados, removidos, ignorados_nao_imagem, erros
            FROM scan_runs ORDER BY id
            """
            ).fetchall()
        ]
        visuais = [
            tuple(row)
            for row in conn.execute(
                """
            SELECT visual_status, COUNT(*) FROM imagens
            WHERE status != 'removido' GROUP BY visual_status
            """
            ).fetchall()
        ]
        crop_ativos = conn.execute(
            "SELECT COUNT(*) FROM imagens WHERE variante='crop' AND status!='removido'"
        ).fetchone()[0]
        zip_ativos = conn.execute(
            """
            SELECT COUNT(*) FROM imagens
            WHERE instr(lower(path), '/0 - arquivos zip/') > 0 AND status!='removido'
            """
        ).fetchone()[0]
        vetores = (
            conn.execute("SELECT COUNT(*) FROM vec_imagens").fetchone()[0]
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='vec_imagens'").fetchone()
            else 0
        )
    finally:
        conn.close()

    classificados = sum(n for nome, n in status if nome == "ok")
    percentual = (classificados / total * 100) if total else 0
    print(f"total={total}")
    print(f"classificados_ok={classificados} ({percentual:.1f}%)")
    print(f"status={status}")
    print(f"tipos={tipos}")
    print(f"com_proxy={proxies}")
    print(f"registros_em_reduzidas={reduzidas_registros}")
    print(f"pendentes_top={pendentes}")
    print("amostras_pendentes=")
    for segmento, paths in amostras.items():
        print(f"  {segmento}: {paths}")
    print(f"runs={runs}")
    print(f"visuais={visuais}")
    print(f"vetores={vetores}")
    print(f"crop_ativos={crop_ativos}")
    print(f"zip_ativos={zip_ativos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
