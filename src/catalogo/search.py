"""Busca semantica texto->imagem sobre sqlite-vec."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from catalogo.db import connect
from catalogo.parser import normalizar_segmento


class TextEmbedder(Protocol):
    def encode_text(self, texto: str) -> Sequence[float]: ...


class ClipTextEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")

    def encode_text(self, texto: str) -> Sequence[float]:
        return self.model.encode(
            texto,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


def buscar_semantica(
    db_path: Path,
    texto: str,
    *,
    embedder: TextEmbedder | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    conn = connect(db_path)
    try:
        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        encoder = embedder or ClipTextEmbedder(config["modelo_embedding"])
        vetor = [float(valor) for valor in encoder.encode_text(texto)]
        if len(vetor) != int(config["embedding_dim"]):
            raise ValueError(f"Embedding de texto com dimensao {len(vetor)}")
        vizinhos = conn.execute(
            """
            SELECT rowid, distance
            FROM vec_imagens
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (json.dumps(vetor), limit),
        ).fetchall()
        resultados = []
        for vizinho in vizinhos:
            imagem = conn.execute(
                """
                SELECT id, path, ano, tipo, colecao, categoria, pessoa, pessoa_tipo,
                       formato_foto, variante, ambiente_tipo, ambiente_tema, paleta_json,
                       cores_comerciais_json, cores_marketing_json
                FROM imagens WHERE id=? AND status!='removido'
                """,
                (vizinho["rowid"],),
            ).fetchone()
            if imagem is None:
                continue
            item = dict(imagem)
            item["distancia"] = float(vizinho["distance"])
            resultados.append(item)
        return resultados
    finally:
        conn.close()


def buscar_por_vetor(
    db_path: Path,
    vetor: Sequence[float],
    *,
    limit: int = 60,
) -> list[dict[str, object]]:
    """Retorna as imagens mais proximas de um vetor visual temporario."""

    conn = connect(db_path)
    try:
        dimensao = int(
            conn.execute("SELECT valor FROM config WHERE chave='embedding_dim'").fetchone()["valor"]
        )
        valores = [float(valor) for valor in vetor]
        if len(valores) != dimensao:
            raise ValueError(f"Embedding de imagem com dimensao {len(valores)}")
        vizinhos = conn.execute(
            """
            SELECT rowid, distance FROM vec_imagens
            WHERE embedding MATCH ? ORDER BY distance LIMIT ?
            """,
            (json.dumps(valores), limit),
        ).fetchall()
        if not vizinhos:
            return []
        ids = [row["rowid"] for row in vizinhos]
        placeholders = ",".join("?" for _ in ids)
        imagens = conn.execute(
            f"""
            SELECT id, path, ano, tipo, colecao, categoria, pessoa, pessoa_tipo,
                   formato_foto, variante, ambiente_tipo, ambiente_tema, paleta_json,
                   cores_comerciais_json, cores_marketing_json
            FROM imagens
            WHERE id IN ({placeholders}) AND status!='removido'
            """,
            ids,
        ).fetchall()
        por_id = {row["id"]: dict(row) for row in imagens}
        resultados = []
        for vizinho in vizinhos:
            item = por_id.get(vizinho["rowid"])
            if item is None:
                continue
            item["distancia"] = float(vizinho["distance"])
            resultados.append(item)
        return resultados
    finally:
        conn.close()


def buscar_hibrida(
    db_path: Path,
    texto: str,
    *,
    embedder: TextEmbedder | None = None,
    limit: int = 20,
    ano: int | Sequence[int] | None = None,
    tipo: str | Sequence[str] | None = None,
    pessoa: str | Sequence[str] | None = None,
    pessoa_tipo: str | Sequence[str] | None = None,
    formato_foto: str | Sequence[str] | None = None,
    categoria: str | Sequence[str] | None = None,
    variante: str | Sequence[str] | None = None,
    cor: str | Sequence[str] | None = None,
    tom: str | Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Combina metadados exatos, FTS do caminho e ranking vetorial."""

    conn = connect(db_path)
    try:
        filtros = _inferir_filtros(
            conn,
            texto,
            ano=ano,
            tipo=tipo,
            pessoa=pessoa,
            pessoa_tipo=pessoa_tipo,
            formato_foto=formato_foto,
            categoria=categoria,
            variante=variante,
            cor=cor,
            tom=tom,
        )
        candidatos = _candidatos_sql(conn, filtros, limit=2000)
        ids_permitidos = set(candidatos)
        if not ids_permitidos:
            return []

        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        encoder = embedder or ClipTextEmbedder(config["modelo_embedding"])
        vetor = [float(valor) for valor in encoder.encode_text(texto)]
        vizinhos = conn.execute(
            """
            SELECT rowid, distance FROM vec_imagens
            WHERE embedding MATCH ? ORDER BY distance LIMIT 2000
            """,
            (json.dumps(vetor),),
        ).fetchall()
        ranking_vetor = {
            row["rowid"]: posicao
            for posicao, row in enumerate(vizinhos, 1)
            if row["rowid"] in ids_permitidos
        }
        ranking_fts = _ranking_fts(conn, texto, filtros, ids_permitidos)

        pontuacoes: dict[int, float] = {}
        for imagem_id in ids_permitidos:
            pontos = 0.0
            if imagem_id in ranking_vetor:
                pontos += 1 / (60 + ranking_vetor[imagem_id])
            if imagem_id in ranking_fts:
                pontos += 2 / (60 + ranking_fts[imagem_id])
            if filtros:
                pontos += 0.001
            pontuacoes[imagem_id] = pontos

        ordenados = sorted(pontuacoes, key=pontuacoes.get, reverse=True)[:limit]
        resultados = []
        for imagem_id in ordenados:
            item = dict(candidatos[imagem_id])
            item["score_hibrido"] = pontuacoes[imagem_id]
            resultados.append(item)
        return resultados
    finally:
        conn.close()


def buscar_semelhantes(
    db_path: Path, imagem_id: int, *, limit: int = 20
) -> list[dict[str, object]]:
    conn = connect(db_path)
    try:
        origem = conn.execute(
            "SELECT embedding FROM vec_imagens WHERE rowid=?", (imagem_id,)
        ).fetchone()
        if origem is None:
            return []
        vizinhos = conn.execute(
            """
            SELECT rowid, distance FROM vec_imagens
            WHERE embedding MATCH ? ORDER BY distance LIMIT ?
            """,
            (origem["embedding"], limit + 1),
        ).fetchall()
        resultados = []
        for vizinho in vizinhos:
            if vizinho["rowid"] == imagem_id:
                continue
            imagem = conn.execute(
                """
                SELECT id, path, ano, tipo, colecao, categoria, pessoa, pessoa_tipo,
                       formato_foto, variante, ambiente_tipo, ambiente_tema, paleta_json,
                       cores_comerciais_json, cores_marketing_json
                FROM imagens WHERE id=? AND status!='removido'
                """,
                (vizinho["rowid"],),
            ).fetchone()
            if imagem is not None:
                item = dict(imagem)
                item["distancia"] = float(vizinho["distance"])
                resultados.append(item)
            if len(resultados) == limit:
                break
        return resultados
    finally:
        conn.close()


def _inferir_filtros(conn, texto: str, **explicitos) -> dict[str, object]:
    normalizado = normalizar_segmento(texto)
    filtros = {
        chave: valor
        for chave, valor in explicitos.items()
        if valor is not None and (not isinstance(valor, (list, tuple, set)) or bool(valor))
    }
    if "pessoa" not in filtros:
        pessoas = conn.execute(
            "SELECT termo FROM vocab_pessoas WHERE length(termo) >= 4 ORDER BY length(termo) DESC"
        ).fetchall()
        filtros["pessoa"] = next(
            (row["termo"] for row in pessoas if row["termo"] in normalizado), None
        )
        if filtros["pessoa"] is None:
            filtros.pop("pessoa")
    if "marketplace internacional" in normalizado:
        filtros.setdefault("formato_foto", "marketplace internacional")
    mapa_tipos = {
        "influenciador": "influenciadores",
        "arquiteto": "arquitetos",
        "quartinho": "quartinhos",
    }
    for termo, valor in mapa_tipos.items():
        if termo in normalizado:
            filtros.setdefault("tipo", valor)
            break
    if "categoria" not in filtros:
        categorias = conn.execute(
            """
            SELECT DISTINCT categoria FROM imagens
            WHERE categoria IS NOT NULL ORDER BY length(categoria) DESC
            """
        ).fetchall()
        encontrada = next(
            (row["categoria"] for row in categorias if row["categoria"] in normalizado), None
        )
        if encontrada:
            filtros["categoria"] = encontrada
    return filtros


def _candidatos_sql(conn, filtros: dict[str, object], *, limit: int) -> dict[int, object]:
    colunas = {"ano", "tipo", "pessoa", "pessoa_tipo", "formato_foto", "categoria", "variante"}
    where = ["status != 'removido'", "visual_status = 'ok'"]
    params: list[object] = []
    for chave, valor in filtros.items():
        valores = valor if isinstance(valor, (list, tuple, set)) else [valor]
        if not valores:
            continue
        if chave in {"cor", "tom"}:
            coluna_cores = "cores_comerciais_json" if chave == "cor" else "cores_marketing_json"
            where.append(
                f"EXISTS (SELECT 1 FROM json_each(imagens.{coluna_cores}) "
                f"WHERE json_extract(value, '$.nome') IN "
                f"({','.join('?' for _ in valores)}))"
            )
            params.extend(valores)
            continue
        if chave not in colunas:
            continue
        where.append(f"{chave} IN ({','.join('?' for _ in valores)})")
        params.extend(valores)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, path, ano, tipo, colecao, categoria, pessoa, pessoa_tipo,
               formato_foto, variante, ambiente_tipo, ambiente_tema, paleta_json,
               cores_comerciais_json, cores_marketing_json
        FROM imagens WHERE {" AND ".join(where)} LIMIT ?
        """,
        params,
    ).fetchall()
    return {row["id"]: row for row in rows}


def _ranking_fts(
    conn, texto: str, filtros: dict[str, object], permitidos: set[int]
) -> dict[int, int]:
    normalizado = normalizar_segmento(texto).replace("quartinho", "quarto")
    stopwords = {"para", "com", "das", "dos", "uma", "foto", "tema"}
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalizado)
        if len(token) >= 3 and token not in stopwords
    ]
    if not tokens:
        return {}
    for operador in (" AND ", " OR "):
        consulta = operador.join(f'"{token}"*' for token in tokens)
        try:
            rows = conn.execute(
                "SELECT rowid FROM imagens_fts WHERE imagens_fts MATCH ? LIMIT 1000",
                (consulta,),
            ).fetchall()
        except Exception:
            continue
        ids = [row["rowid"] for row in rows if row["rowid"] in permitidos]
        if ids:
            return {imagem_id: posicao for posicao, imagem_id in enumerate(ids, 1)}
    return {}
