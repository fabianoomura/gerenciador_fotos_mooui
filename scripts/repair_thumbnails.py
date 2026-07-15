"""Reconstrói thumbnails ausentes sem recalcular paletas ou embeddings."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def gerar(row: sqlite3.Row, *, thumbs_dir: Path, size: int, quality: int) -> str:
    destino = Path(row["thumb_path"] or thumbs_dir / f"{row['id']}.jpg")
    if destino.is_file():
        return "existente"

    origem = next(
        (
            Path(candidato)
            for candidato in (row["reduzida_path"], row["path"])
            if candidato and Path(candidato).is_file()
        ),
        None,
    )
    if origem is None:
        return "sem_origem"

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    try:
        with Image.open(origem) as aberta:
            imagem = ImageOps.exif_transpose(aberta).convert("RGB")
            imagem.thumbnail((size, size))
            imagem.save(temporario, "JPEG", quality=quality, optimize=True)
        temporario.replace(destino)
        return "gerada"
    except Exception:
        temporario.unlink(missing_ok=True)
        return "erro"


def main() -> None:
    args = argumentos()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    config = {
        row["chave"]: row["valor"]
        for row in conn.execute(
            "SELECT chave, valor FROM config WHERE chave IN "
            "('thumbs_dir', 'thumb_size', 'thumb_quality')"
        )
    }
    where = ["status!='removido'"]
    params: list[object] = []
    if args.year is not None:
        where.append("ano=?")
        params.append(args.year)
    sql = (
        "SELECT id, path, reduzida_path, thumb_path FROM imagens "
        f"WHERE {' AND '.join(where)} ORDER BY id DESC"
    )
    if args.limit is not None:
        sql += " LIMIT ?"
        params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    thumbs_dir = Path(config["thumbs_dir"])
    resultados = {"gerada": 0, "existente": 0, "sem_origem": 0, "erro": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futuros = [
            executor.submit(
                gerar,
                row,
                thumbs_dir=thumbs_dir,
                size=int(config["thumb_size"]),
                quality=int(config["thumb_quality"]),
            )
            for row in rows
        ]
        for futuro in as_completed(futuros):
            resultados[futuro.result()] += 1
    print(json.dumps(resultados, ensure_ascii=False))


if __name__ == "__main__":
    main()
