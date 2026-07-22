"""Recalcula cores de produtos sem refazer embeddings CLIP."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.db import bootstrap, connect  # noqa: E402
from catalogo.palette import extrair_paleta_produto, simplificar_cores  # noqa: E402


def _abrir_imagem(
    row,
    max_size: int,
    *,
    trusted_large_images: bool = False,
    allow_truncated: bool = False,
) -> Image.Image:
    candidatos = (row["reduzida_path"], row["thumb_path"], row["path"])
    for valor in candidatos:
        if valor and Path(valor).is_file():
            max_pixels_anterior = Image.MAX_IMAGE_PIXELS
            truncadas_anterior = ImageFile.LOAD_TRUNCATED_IMAGES
            try:
                if trusted_large_images:
                    Image.MAX_IMAGE_PIXELS = None
                if allow_truncated:
                    ImageFile.LOAD_TRUNCATED_IMAGES = True
                with Image.open(valor) as origem:
                    # JPEG consegue reduzir na decodificacao, evitando centenas de
                    # milhoes de pixels na memoria para paineis muito largos.
                    origem.draft("RGB", (max_size, max_size))
                    imagem = origem.convert("RGB")
            finally:
                Image.MAX_IMAGE_PIXELS = max_pixels_anterior
                ImageFile.LOAD_TRUNCATED_IMAGES = truncadas_anterior
            imagem.thumbnail((max_size, max_size))
            return imagem
    raise FileNotFoundError(row["path"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("catalogo.db"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--trusted-large-images", action="store_true")
    parser.add_argument("--allow-truncated", action="store_true")
    args = parser.parse_args()

    bootstrap(args.db)
    conn = connect(args.db)
    try:
        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        sql = """
            SELECT id, path, reduzida_path, thumb_path
            FROM imagens
            WHERE status != 'removido' AND lower(tipo) LIKE 'produto%'
        """
        if args.only_missing:
            sql += " AND paleta_produto_json IS NULL"
        sql += " ORDER BY id"
        params: tuple[int, ...] = ()
        if args.limit is not None:
            sql += " LIMIT ?"
            params = (args.limit,)
        rows = conn.execute(sql, params).fetchall()
        referencias = json.loads(config["cores_comerciais"])
        referencias_marketing = json.loads(config["cores_marketing"])
        paleta_k = int(config["paleta_k"])
        max_size = int(config["thumb_size"])

        def processar(row):
            imagem = _abrir_imagem(
                row,
                max_size,
                trusted_large_images=args.trusted_large_images,
                allow_truncated=args.allow_truncated,
            )
            try:
                paleta = extrair_paleta_produto(imagem, k=paleta_k)
            finally:
                imagem.close()
            cores = simplificar_cores(
                paleta,
                referencias,
                max_cores=int(config["cores_comerciais_max"]),
                min_proporcao=float(config["cores_comerciais_min_proporcao"]),
            )
            marketing = simplificar_cores(
                paleta,
                referencias_marketing,
                max_cores=int(config["cores_marketing_max"]),
                min_proporcao=float(config["cores_marketing_min_proporcao"]),
            )
            return row["id"], paleta, cores, marketing

        processadas = 0
        erros = 0
        workers = args.workers or int(config["io_workers"])
        for inicio in range(0, len(rows), args.batch_size):
            lote = rows[inicio : inicio + args.batch_size]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futuros = {executor.submit(processar, row): row["id"] for row in lote}
                for futuro in as_completed(futuros):
                    try:
                        imagem_id, paleta, cores, marketing = futuro.result()
                        conn.execute(
                            """
                            UPDATE imagens
                            SET paleta_produto_json=?, cores_comerciais_json=?,
                                cores_marketing_json=?, atualizado_em=unixepoch('subsec')
                            WHERE id=?
                            """,
                            (
                                json.dumps(paleta, ensure_ascii=False),
                                json.dumps(cores, ensure_ascii=False),
                                json.dumps(marketing, ensure_ascii=False),
                                imagem_id,
                            ),
                        )
                        processadas += 1
                    except Exception as exc:
                        erros += 1
                        print(
                            f"erro id={futuros[futuro]}: {type(exc).__name__}: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
            conn.commit()
            print(
                f"progresso={processadas + erros}/{len(rows)} "
                f"processadas={processadas} erros={erros}",
                flush=True,
            )
        return 0 if erros == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
