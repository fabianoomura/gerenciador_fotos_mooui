"""API HTTP somente leitura do catálogo visual."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from catalogo.db import connect
from catalogo.filtros import (
    CAMPOS_FILTRO,
    VALORES_VALIDOS,
    construir_filtros_sql,
)
from catalogo.search import (
    ClipTextEmbedder,
    buscar_hibrida,
    buscar_por_vetor,
    buscar_semelhantes,
)
from catalogo.visual import ClipImageEmbedder

API_VERSION = "2"

# Parametros aceitos por /busca alem dos filtros; qualquer outro retorna 422
# em vez de ser ignorado em silencio.
_PARAMS_BUSCA = CAMPOS_FILTRO | {"q", "limit", "offset"}


class SearchService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._embedder = None

    def __call__(self, texto: str, **filtros):
        if self._embedder is None:
            conn = connect(self.db_path)
            try:
                modelo = conn.execute(
                    "SELECT valor FROM config WHERE chave='modelo_embedding'"
                ).fetchone()["valor"]
            finally:
                conn.close()
            self._embedder = ClipTextEmbedder(modelo)
        return buscar_hibrida(self.db_path, texto, embedder=self._embedder, **filtros)


class ImageSearchService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._embedder = None

    def __call__(self, imagem: Image.Image, *, limit: int):
        if self._embedder is None:
            conn = connect(self.db_path)
            try:
                modelo = conn.execute(
                    "SELECT valor FROM config WHERE chave='modelo_embedding_imagem'"
                ).fetchone()["valor"]
            finally:
                conn.close()
            self._embedder = ClipImageEmbedder(modelo, batch_size=1)
        vetor = self._embedder.encode_images([imagem])[0]
        return buscar_por_vetor(self.db_path, vetor, limit=limit)


def create_app(
    db_path: Path | str = "catalogo.db",
    *,
    searcher: Callable | None = None,
    image_searcher: Callable | None = None,
    cors_origins: list[str] | None = None,
    api_token: str | None = None,
) -> FastAPI:
    db = Path(db_path)
    buscar = searcher or SearchService(db)
    buscar_imagem = image_searcher or ImageSearchService(db)
    app = FastAPI(title="Catálogo Visual de Fotos", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    if api_token:

        @app.middleware("http")
        async def exigir_token(request: Request, call_next):
            recebido = request.headers.get("authorization", "")
            esperado = f"Bearer {api_token}"
            if not secrets.compare_digest(recebido, esperado):
                return JSONResponse({"detail": "Não autorizado"}, status_code=401)
            return await call_next(request)

    @app.get("/health")
    def health():
        conn = connect(db)
        try:
            ativas = conn.execute(
                "SELECT COUNT(*) FROM imagens WHERE status!='removido'"
            ).fetchone()[0]
        finally:
            conn.close()
        return {"status": "ok", "imagens_ativas": ativas}

    @app.get("/busca")
    def busca(
        request: Request,
        q: str | None = None,
        ano: list[int] | None = Query(None),
        tipo: list[str] | None = Query(None),
        colecao: list[str] | None = Query(None),
        categoria: list[str] | None = Query(None),
        pessoa: list[str] | None = Query(None),
        pessoa_tipo: list[str] | None = Query(None),
        ambiente_tipo: list[str] | None = Query(None),
        ambiente_tema: list[str] | None = Query(None),
        drop_tema: list[str] | None = Query(None),
        formato_foto: list[str] | None = Query(None),
        variante: list[str] | None = Query(None),
        orientacao: list[str] | None = Query(None),
        possui_pessoa: str | None = Query(None),
        possui_modelo: str | None = Query(None),
        direitos_uso_status: list[str] | None = Query(None),
        cor: list[str] | None = Query(None),
        tom: list[str] | None = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        _rejeitar_params_desconhecidos(request)
        filtros = {
            "ano": ano,
            "tipo": tipo,
            "colecao": colecao,
            "categoria": categoria,
            "pessoa": pessoa,
            "pessoa_tipo": pessoa_tipo,
            "ambiente_tipo": ambiente_tipo,
            "ambiente_tema": ambiente_tema,
            "drop_tema": drop_tema,
            "formato_foto": formato_foto,
            "variante": variante,
            "orientacao": orientacao,
            "possui_pessoa": possui_pessoa,
            "possui_modelo": possui_modelo,
            "direitos_uso_status": direitos_uso_status,
            "cor": cor,
            "tom": tom,
        }
        try:
            if q:
                candidatos = buscar(q, limit=limit + offset + 1, **filtros)
                itens = candidatos[offset : offset + limit]
                total = None
                has_more = len(candidatos) > offset + limit
            else:
                itens = _listar_sql(db, filtros, limit=limit, offset=offset)
                total = _contar_sql(db, filtros)
                has_more = offset + len(itens) < total
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        aplicados = {
            campo: valor if isinstance(valor, list) else [valor]
            for campo, valor in filtros.items()
            if valor is not None and valor != []
        }
        return {
            "items": [_serializar(item) for item in itens],
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": has_more,
            "applied_filters": aplicados,
            "ignored_filters": [],
        }

    @app.get("/capabilities")
    def capabilities():
        return {
            "api_version": API_VERSION,
            "search_mode": ["metadata", "fts", "vector", "hybrid"],
            "filters": {
                "ano": "integer",
                "tipo": "string",
                "colecao": "string",
                "categoria": "string",
                "pessoa": "string",
                "pessoa_tipo": [
                    "arquiteto",
                    "influenciador",
                    "modelo",
                    "fotografo",
                    "parceiro",
                ],
                "ambiente_tipo": "string",
                "ambiente_tema": "string",
                "drop_tema": "string",
                "formato_foto": "string",
                "variante": "string",
                "cor": "string",
                "tom": "string",
                "orientacao": sorted(VALORES_VALIDOS["orientacao"]),
                "possui_pessoa": "boolean",
                "possui_modelo": "boolean",
                "direitos_uso_status": sorted(VALORES_VALIDOS["direitos_uso_status"]),
            },
            "filter_values_endpoint": "/facetas",
            "color_values_endpoint": "/paleta/swatches",
            "supports_negative_filters": True,
            "negative_filter_syntax": "prefixe o valor com ! (ex.: pessoa_tipo=!modelo)",
            "unknown_filters": "retornam 422; nada e ignorado em silencio",
            "notes": {
                "possui_modelo": "true equivale a pessoa_tipo=modelo; false exclui modelos",
                "possui_pessoa": "tri-estado: NULL no banco significa desconhecido "
                "e nao casa com true nem false",
                "direitos_uso_status": "nunca inferido por IA; unknown ate revisao humana",
            },
            "pagination": {"limit_max": 100},
        }

    @app.post("/busca/por-imagem")
    async def busca_por_imagem(
        request: Request,
        limit: int = Query(60, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="Envie um arquivo de imagem")
        conn = connect(db)
        try:
            config = {
                row["chave"]: row["valor"]
                for row in conn.execute(
                    "SELECT chave, valor FROM config WHERE chave IN "
                    "('busca_imagem_max_bytes', 'thumb_size')"
                )
            }
        finally:
            conn.close()
        conteudo = await request.body()
        if len(conteudo) > int(config["busca_imagem_max_bytes"]):
            raise HTTPException(status_code=413, detail="Imagem acima do limite permitido")
        try:
            with Image.open(BytesIO(conteudo)) as origem:
                imagem = origem.convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=422, detail="Imagem invalida ou corrompida") from exc
        tamanho = int(config["thumb_size"])
        imagem.thumbnail((tamanho, tamanho))
        try:
            candidatos = await run_in_threadpool(buscar_imagem, imagem, limit=limit + offset + 1)
        finally:
            imagem.close()
        itens = candidatos[offset : offset + limit]
        return {
            "items": [_serializar(item) for item in itens],
            "limit": limit,
            "offset": offset,
            "total": None,
            "has_more": len(candidatos) > offset + limit,
        }

    @app.get("/imagens/{imagem_id}")
    def detalhe(imagem_id: int):
        item = _imagem_por_id(db, imagem_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        return _serializar(item)

    @app.get("/imagens/{imagem_id}/semelhantes")
    def semelhantes(imagem_id: int, limit: int = Query(20, ge=1, le=100)):
        if _imagem_por_id(db, imagem_id) is None:
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        return {
            "items": [_serializar(item) for item in buscar_semelhantes(db, imagem_id, limit=limit)]
        }

    @app.get("/imagens/{imagem_id}/download")
    def download(imagem_id: int):
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT path FROM imagens WHERE id=? AND status!='removido'",
                (imagem_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        path = Path(row["path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Arquivo original indisponível")
        return FileResponse(
            path,
            filename=path.name,
            content_disposition_type="attachment",
        )

    @app.get("/imagens/{imagem_id}/thumb")
    def thumb(imagem_id: int):
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT thumb_path, reduzida_path, path FROM imagens "
                "WHERE id=? AND status!='removido'",
                (imagem_id,),
            ).fetchone()
            thumbs_dir_row = conn.execute(
                "SELECT valor FROM config WHERE chave='thumbs_dir'"
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        # Nem toda imagem possui thumbnail derivada. Depois de uma reinicializacao,
        # o acervo CIFS tambem pode voltar antes do diretorio local de thumbnails.
        # Use o primeiro arquivo realmente disponivel, em vez de parar no primeiro
        # caminho preenchido no banco.
        cache_local = (
            Path(thumbs_dir_row["valor"]) / f"{imagem_id}.jpg"
            if thumbs_dir_row is not None
            else None
        )
        for candidato in (
            row["thumb_path"],
            cache_local,
            row["reduzida_path"],
            row["path"],
        ):
            if candidato:
                path = Path(candidato)
                if path.is_file():
                    return FileResponse(path)
        raise HTTPException(status_code=404, detail="Thumbnail indisponível")

    @app.get("/facetas")
    def facetas():
        conn = connect(db)
        try:
            return {
                campo: [
                    dict(row)
                    for row in conn.execute(
                        f"""
                    SELECT {campo} AS valor, COUNT(*) AS total FROM imagens
                    WHERE status!='removido' AND {campo} IS NOT NULL
                    GROUP BY {campo} ORDER BY total DESC
                    """
                    )
                ]
                for campo in (
                    "ano",
                    "tipo",
                    "colecao",
                    "categoria",
                    "pessoa",
                    "pessoa_tipo",
                    "variante",
                )
            }
        finally:
            conn.close()

    @app.get("/paleta/swatches")
    def swatches(
        limit: int = Query(24, ge=1, le=100),
        modo: str = Query("comercial", pattern="^(comercial|marketing)$"),
    ):
        chave = "cores_comerciais" if modo == "comercial" else "cores_marketing"
        conn = connect(db)
        try:
            referencias = json.loads(
                conn.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()["valor"]
            )
        finally:
            conn.close()
        return {"items": referencias[:limit], "modo": modo}

    return app


def _listar_sql(db: Path, filtros: dict[str, object], *, limit: int, offset: int):
    where, params = _filtros_sql(filtros)
    params.extend((limit, offset))
    conn = connect(db)
    try:
        return conn.execute(
            f"SELECT * FROM imagens WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    finally:
        conn.close()


def _contar_sql(db: Path, filtros: dict[str, object]) -> int:
    where, params = _filtros_sql(filtros)
    conn = connect(db)
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM imagens WHERE {' AND '.join(where)}",
            params,
        ).fetchone()[0]
    finally:
        conn.close()


def _filtros_sql(filtros: dict[str, object]) -> tuple[list[str], list[object]]:
    where = ["status!='removido'"]
    clausulas, params = construir_filtros_sql(filtros)
    where.extend(clausulas)
    return where, params


def _rejeitar_params_desconhecidos(request: Request) -> None:
    """Contrato V2: filtros desconhecidos retornam 422 em vez de sumir em silencio."""

    desconhecidos = sorted(set(request.query_params.keys()) - _PARAMS_BUSCA)
    if desconhecidos:
        raise HTTPException(
            status_code=422,
            detail={
                "mensagem": "Filtros desconhecidos; nenhum parametro e ignorado em silencio",
                "filtros_desconhecidos": desconhecidos,
                "filtros_validos": sorted(_PARAMS_BUSCA),
            },
        )


def _imagem_por_id(db: Path, imagem_id: int):
    conn = connect(db)
    try:
        return conn.execute(
            "SELECT * FROM imagens WHERE id=? AND status!='removido'", (imagem_id,)
        ).fetchone()
    finally:
        conn.close()


def _serializar(item):
    resultado = dict(item)
    if resultado.get("paleta_json"):
        resultado["paleta"] = json.loads(resultado.pop("paleta_json"))
    if resultado.get("cores_comerciais_json"):
        resultado["cores_comerciais"] = json.loads(resultado.pop("cores_comerciais_json"))
        resultado["google_color"] = "/".join(cor["nome"] for cor in resultado["cores_comerciais"])
    if resultado.get("cores_marketing_json"):
        resultado["cores_marketing"] = json.loads(resultado.pop("cores_marketing_json"))
    return resultado


app = create_app()
