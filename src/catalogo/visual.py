"""Paleta e embeddings visuais em lotes incrementais."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from catalogo.db import bootstrap, connect
from catalogo.palette import extrair_paleta, extrair_paleta_produto, simplificar_cores


class ImageEmbedder(Protocol):
    def encode_images(self, imagens: Sequence[Image.Image]) -> Sequence[Sequence[float]]: ...


@dataclass(slots=True)
class VisualResult:
    processadas: int = 0
    erros: int = 0


class ClipImageEmbedder:
    """Encoder visual CLIP carregado sob demanda."""

    def __init__(self, model_name: str, *, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
        self.batch_size = batch_size

    def encode_images(self, imagens: Sequence[Image.Image]) -> Sequence[Sequence[float]]:
        return self.model.encode(
            list(imagens),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


def processar_visuais(
    db_path: Path,
    *,
    embedder: ImageEmbedder | None = None,
    batch_size: int | None = None,
    limit: int | None = None,
    progress_callback: Callable[[VisualResult, int], None] | None = None,
) -> VisualResult:
    """Processa itens pendentes, priorizando o proxy REDUZIDA salvo no banco."""

    bootstrap(db_path)
    conn = connect(db_path)
    try:
        if not _tabela_existe(conn, "vec_imagens"):
            raise RuntimeError("sqlite-vec nao esta carregado; instale o extra [visual]")
        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        tamanho_lote = batch_size or int(config["batch_size"])
        encoder = embedder or ClipImageEmbedder(
            config["modelo_embedding_imagem"], batch_size=tamanho_lote
        )
        sql = """
            SELECT id, path, reduzida_path, thumb_path, tipo
            FROM imagens
            WHERE status != 'removido' AND visual_status != 'ok'
            ORDER BY (reduzida_path IS NULL), id
        """
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(sql, params).fetchall()
        resumo = VisualResult()
        for inicio in range(0, len(rows), tamanho_lote):
            _processar_lote(conn, rows[inicio : inicio + tamanho_lote], encoder, resumo, config)
            conn.commit()
            if progress_callback is not None:
                progress_callback(resumo, len(rows))
        return resumo
    finally:
        conn.close()


def _processar_lote(conn, rows, embedder, resumo: VisualResult, config: dict[str, str]) -> None:
    preparados: list[
        tuple[
            int,
            Image.Image,
            list[dict[str, object]],
            list[dict[str, object]],
            list[dict[str, object]],
            list[dict[str, object]],
        ]
    ] = []
    referencias = json.loads(config["cores_comerciais"])
    referencias_marketing = json.loads(config["cores_marketing"])

    def carregar(row):
        imagem, thumb_path = _carregar_imagem(row, config)
        paleta = extrair_paleta(imagem, k=int(config["paleta_k"]))
        eh_produto = str(row["tipo"] or "").casefold().startswith("produto")
        paleta_produto = (
            extrair_paleta_produto(imagem, k=int(config["paleta_k"]))
            if eh_produto
            else paleta
        )
        cores = simplificar_cores(
            paleta_produto,
            referencias,
            max_cores=int(config["cores_comerciais_max"]),
            min_proporcao=float(config["cores_comerciais_min_proporcao"]),
        )
        cores_marketing = simplificar_cores(
            paleta_produto,
            referencias_marketing,
            max_cores=int(config["cores_marketing_max"]),
            min_proporcao=float(config["cores_marketing_min_proporcao"]),
        )
        return row, imagem, thumb_path, paleta, paleta_produto, cores, cores_marketing

    with ThreadPoolExecutor(max_workers=int(config["io_workers"])) as executor:
        futuros = [(row, executor.submit(carregar, row)) for row in rows]
    for row, futuro in futuros:
        try:
            _, imagem, thumb_path, paleta, paleta_produto, cores, cores_marketing = futuro.result()
            if thumb_path is not None:
                conn.execute("UPDATE imagens SET thumb_path=? WHERE id=?", (thumb_path, row["id"]))
            preparados.append(
                (row["id"], imagem, paleta, paleta_produto, cores, cores_marketing)
            )
        except Exception as exc:  # Pillow pode emitir varios tipos para arquivo corrompido
            conn.execute(
                "UPDATE imagens SET visual_status='erro', visual_erro=? WHERE id=?",
                (f"{type(exc).__name__}: {exc}"[:500], row["id"]),
            )
            resumo.erros += 1

    if not preparados:
        return
    try:
        vetores = embedder.encode_images([item[1] for item in preparados])
        for (imagem_id, imagem, paleta, paleta_produto, cores, cores_marketing), vetor in zip(
            preparados, vetores, strict=True
        ):
            valores = [float(valor) for valor in vetor]
            if len(valores) != int(config["embedding_dim"]):
                raise ValueError(f"Embedding com dimensao {len(valores)}")
            conn.execute("DELETE FROM vec_imagens WHERE rowid = ?", (imagem_id,))
            conn.execute(
                "INSERT INTO vec_imagens(rowid, embedding) VALUES (?, ?)",
                (imagem_id, json.dumps(valores)),
            )
            conn.execute(
                """
                UPDATE imagens
                SET paleta_json=?, paleta_produto_json=?, cores_comerciais_json=?,
                    cores_marketing_json=?,
                    visual_status='ok',
                    visual_erro=NULL, atualizado_em=unixepoch('subsec')
                WHERE id=?
                """,
                (
                    json.dumps(paleta, ensure_ascii=False),
                    json.dumps(paleta_produto, ensure_ascii=False),
                    json.dumps(cores, ensure_ascii=False),
                    json.dumps(cores_marketing, ensure_ascii=False),
                    imagem_id,
                ),
            )
            imagem.close()
            resumo.processadas += 1
    except Exception as exc:
        for imagem_id, imagem, _, _, _, _ in preparados:
            imagem.close()
            conn.execute(
                "UPDATE imagens SET visual_status='erro', visual_erro=? WHERE id=?",
                (f"{type(exc).__name__}: {exc}"[:500], imagem_id),
            )
            resumo.erros += 1


def _tabela_existe(conn, nome: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (nome,)).fetchone() is not None
    )


def _carregar_imagem(row, config: dict[str, str]) -> tuple[Image.Image, str | None]:
    """Usa REDUZIDA, thumbnail em cache ou gera uma thumbnail fora do share."""

    if row["reduzida_path"]:
        with Image.open(row["reduzida_path"]) as aberta:
            imagem = aberta.convert("RGB")
        tamanho = int(config["thumb_size"])
        imagem.thumbnail((tamanho, tamanho))
        return imagem, None

    thumb_existente = Path(row["thumb_path"]) if row["thumb_path"] else None
    if thumb_existente and thumb_existente.is_file():
        with Image.open(thumb_existente) as aberta:
            imagem = aberta.convert("RGB")
        tamanho = int(config["thumb_size"])
        imagem.thumbnail((tamanho, tamanho))
        return imagem, str(thumb_existente)

    thumbs_dir = Path(config["thumbs_dir"])
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    destino = thumbs_dir / f"{row['id']}.jpg"
    with Image.open(row["path"]) as aberta:
        imagem = aberta.convert("RGB")
    tamanho = int(config["thumb_size"])
    imagem.thumbnail((tamanho, tamanho))
    temporario = destino.with_suffix(".tmp.jpg")
    imagem.save(temporario, "JPEG", quality=int(config["thumb_quality"]), optimize=True)
    temporario.replace(destino)
    return imagem, str(destino)
