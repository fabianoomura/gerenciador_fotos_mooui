"""Busca semantica texto->imagem sobre sqlite-vec."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from catalogo.db import connect
from catalogo.filtros import construir_filtros_sql
from catalogo.parser import normalizar_segmento
from catalogo.sinonimos import carregar_grupos, expandir_tokens

_COLUNAS_RESULTADO = """
    id, path, ano, tipo, colecao, categoria, pessoa, pessoa_tipo,
    formato_foto, variante, ambiente_tipo, ambiente_tema, drop_tema,
    largura, altura, orientacao, possui_pessoa, direitos_uso_status,
    paleta_json, cores_comerciais_json, cores_marketing_json
"""


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
                f"""
                SELECT {_COLUNAS_RESULTADO}
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
            SELECT {_COLUNAS_RESULTADO}
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
    colecao: str | Sequence[str] | None = None,
    pessoa: str | Sequence[str] | None = None,
    pessoa_tipo: str | Sequence[str] | None = None,
    formato_foto: str | Sequence[str] | None = None,
    categoria: str | Sequence[str] | None = None,
    variante: str | Sequence[str] | None = None,
    ambiente_tipo: str | Sequence[str] | None = None,
    ambiente_tema: str | Sequence[str] | None = None,
    drop_tema: str | Sequence[str] | None = None,
    orientacao: str | Sequence[str] | None = None,
    possui_pessoa: bool | str | None = None,
    possui_modelo: bool | str | None = None,
    direitos_uso_status: str | Sequence[str] | None = None,
    cor: str | Sequence[str] | None = None,
    tom: str | Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Combina metadados exatos, FTS do caminho e ranking vetorial.

    Os filtros restringem os candidatos ANTES do ranking FTS/vetorial, para
    nao eliminar resultados relevantes depois do top-k.
    """

    conn = connect(db_path)
    try:
        filtros = _inferir_filtros(
            conn,
            texto,
            ano=ano,
            tipo=tipo,
            colecao=colecao,
            pessoa=pessoa,
            pessoa_tipo=pessoa_tipo,
            formato_foto=formato_foto,
            categoria=categoria,
            variante=variante,
            ambiente_tipo=ambiente_tipo,
            ambiente_tema=ambiente_tema,
            drop_tema=drop_tema,
            orientacao=orientacao,
            possui_pessoa=possui_pessoa,
            possui_modelo=possui_modelo,
            direitos_uso_status=direitos_uso_status,
            cor=cor,
            tom=tom,
        )
        clausulas, params_filtro = construir_filtros_sql(filtros)
        tem_filtros = bool(clausulas)

        # Ramo textual: FTS sobre o caminho/metadados, expandido por sinonimos e
        # ordenado por bm25. Os candidatos vem das proprias correspondencias de
        # texto e vetor (nao de um lote arbitrario), respeitando os filtros.
        tokens_extra = expandir_tokens(texto, carregar_grupos(conn))
        fts_ids = _fts_ranked_ids(conn, texto, tokens_extra, limit=2000)
        fts_permitidos = _permitir(conn, fts_ids, clausulas, params_filtro)
        ranking_fts = {
            imagem_id: posicao
            for posicao, imagem_id in enumerate(
                (i for i in fts_ids if i in fts_permitidos), 1
            )
        }

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
        vec_ids = [row["rowid"] for row in vizinhos]
        vec_permitidos = _permitir(conn, vec_ids, clausulas, params_filtro)
        ranking_vetor = {
            imagem_id: posicao
            for posicao, imagem_id in enumerate(
                (i for i in vec_ids if i in vec_permitidos), 1
            )
        }

        ids = set(ranking_fts) | set(ranking_vetor)
        if ids:
            candidatos = _buscar_rows(conn, ids)
        elif tem_filtros:
            # Texto nao casou, mas ha filtros: devolve o universo do filtro.
            candidatos = _candidatos_sql(conn, filtros, limit=limit * 3)
            ids = set(candidatos)
        if not ids:
            return []

        pontuacoes: dict[int, float] = {}
        for imagem_id in ids:
            pontos = 0.0
            if imagem_id in ranking_vetor:
                pontos += 1 / (60 + ranking_vetor[imagem_id])
            if imagem_id in ranking_fts:
                pontos += 2 / (60 + ranking_fts[imagem_id])
            if tem_filtros:
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
                f"""
                SELECT {_COLUNAS_RESULTADO}
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
    where = ["status != 'removido'", "visual_status = 'ok'"]
    clausulas, params = construir_filtros_sql(filtros)
    where.extend(clausulas)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT {_COLUNAS_RESULTADO}
        FROM imagens WHERE {" AND ".join(where)} LIMIT ?
        """,
        params,
    ).fetchall()
    return {row["id"]: row for row in rows}


def _tokens_consulta(texto: str) -> list[str]:
    normalizado = normalizar_segmento(texto).replace("quartinho", "quarto")
    stopwords = {"para", "com", "das", "dos", "uma", "foto", "tema"}
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalizado)
        if len(token) >= 3 and token not in stopwords
    ]


def _fts_ranked_ids(
    conn, texto: str, tokens_extra: set[str], *, limit: int
) -> list[int]:
    """IDs ordenados por relevancia bm25 do FTS, com expansao por sinonimos."""

    tokens = _tokens_consulta(texto)
    todos = tokens + [token for token in sorted(tokens_extra) if token not in tokens]
    if not todos:
        return []
    consulta = " OR ".join(f'"{token}"*' for token in todos)
    try:
        rows = conn.execute(
            "SELECT rowid FROM imagens_fts WHERE imagens_fts MATCH ? ORDER BY rank LIMIT ?",
            (consulta, limit),
        ).fetchall()
    except Exception:
        return []
    return [row["rowid"] for row in rows]


def _em_lotes(ids, tamanho=800):
    ids = list(ids)
    for inicio in range(0, len(ids), tamanho):
        yield ids[inicio : inicio + tamanho]


def _permitir(
    conn, ids: list[int], clausulas: list[str], params_filtro: list[object]
) -> set[int]:
    """Filtra ids por status/visual e pelos filtros estruturais."""

    if not ids:
        return set()
    where = ["status != 'removido'", "visual_status = 'ok'", *clausulas]
    permitidos: set[int] = set()
    for lote in _em_lotes(ids):
        marcadores = ",".join("?" for _ in lote)
        rows = conn.execute(
            f"SELECT id FROM imagens WHERE id IN ({marcadores}) AND {' AND '.join(where)}",
            [*lote, *params_filtro],
        ).fetchall()
        permitidos.update(row["id"] for row in rows)
    return permitidos


def _buscar_rows(conn, ids: set[int]) -> dict[int, object]:
    resultado: dict[int, object] = {}
    for lote in _em_lotes(ids):
        marcadores = ",".join("?" for _ in lote)
        rows = conn.execute(
            f"SELECT {_COLUNAS_RESULTADO} FROM imagens "
            f"WHERE id IN ({marcadores}) AND status != 'removido'",
            lote,
        ).fetchall()
        resultado.update((row["id"], row) for row in rows)
    return resultado
