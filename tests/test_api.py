"""Testes de integração HTTP da API somente leitura."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from catalogo.api import create_app
from catalogo.db import connect
from catalogo.indexer import indexar_metadados
from catalogo.visual import processar_visuais


class FakeImageEmbedder:
    def encode_images(self, imagens):
        return [[1.0] + [0.0] * 511 for _ in imagens]


def _cliente(tmp_path: Path) -> tuple[TestClient, Path, int]:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2026" / "COLECAO 2026 - PRODUTOS" / "BONECAS" / "boneca.png"
    foto.parent.mkdir(parents=True)
    Image.new("RGB", (3, 3), "red").save(foto)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    conn = connect(db)
    try:
        conn.execute(
            "UPDATE config SET valor=? WHERE chave='thumbs_dir'", (str(tmp_path / "thumbs"),)
        )
        conn.commit()
        imagem_id = conn.execute("SELECT id FROM imagens").fetchone()[0]
    finally:
        conn.close()
    processar_visuais(db, embedder=FakeImageEmbedder())

    def busca_falsa(texto, **kwargs):
        conn = connect(db)
        try:
            return [dict(conn.execute("SELECT * FROM imagens").fetchone())]
        finally:
            conn.close()

    def busca_imagem_falsa(imagem, **kwargs):
        assert imagem.mode == "RGB"
        conn = connect(db)
        try:
            return [dict(conn.execute("SELECT * FROM imagens").fetchone())]
        finally:
            conn.close()

    return (
        TestClient(create_app(db, searcher=busca_falsa, image_searcher=busca_imagem_falsa)),
        foto,
        imagem_id,
    )


def test_health_busca_e_detalhe(tmp_path: Path) -> None:
    cliente, foto, imagem_id = _cliente(tmp_path)

    assert cliente.get("/health").json() == {"status": "ok", "imagens_ativas": 1}
    busca = cliente.get("/busca", params={"q": "boneca vermelha"})
    assert busca.status_code == 200
    assert busca.json()["items"][0]["path"] == str(foto)
    detalhe = cliente.get(f"/imagens/{imagem_id}")
    assert detalhe.status_code == 200
    assert detalhe.json()["paleta"][0]["hex"] == "#FF0000"
    assert detalhe.json()["google_color"] == "Vermelho"

    por_imagem = cliente.post(
        "/busca/por-imagem",
        content=foto.read_bytes(),
        headers={"content-type": "image/png"},
    )
    assert por_imagem.status_code == 200
    assert por_imagem.json()["items"][0]["path"] == str(foto)
    assert cliente.post("/busca/por-imagem", content=b"texto").status_code == 415


def test_filtros_facetas_thumb_e_404(tmp_path: Path) -> None:
    cliente, foto, imagem_id = _cliente(tmp_path)

    resposta = cliente.get("/busca", params={"ano": 2026, "tipo": "produtos"})
    assert len(resposta.json()["items"]) == 1
    assert resposta.json()["total"] == 1
    assert resposta.json()["has_more"] is False
    segunda_pagina = cliente.get("/busca", params={"limit": 1, "offset": 1})
    assert segunda_pagina.json()["items"] == []
    varios_anos = cliente.get("/busca?ano=2025&ano=2026")
    assert len(varios_anos.json()["items"]) == 1
    conn = connect(tmp_path / "catalogo.db")
    try:
        conn.execute("UPDATE imagens SET pessoa_tipo='influenciador' WHERE id=?", (imagem_id,))
        conn.commit()
    finally:
        conn.close()
    varios_perfis = cliente.get("/busca?pessoa_tipo=arquiteto&pessoa_tipo=influenciador")
    assert len(varios_perfis.json()["items"]) == 1
    por_cor = cliente.get("/busca", params={"cor": "Vermelho"})
    assert len(por_cor.json()["items"]) == 1
    facetas = cliente.get("/facetas").json()
    assert facetas["tipo"][0] == {"valor": "produtos", "total": 1}
    assert cliente.get(f"/imagens/{imagem_id}/thumb").status_code == 200
    download = cliente.get(f"/imagens/{imagem_id}/download")
    assert download.status_code == 200
    assert download.content == foto.read_bytes()
    assert download.headers["content-disposition"].startswith("attachment;")
    nomes_comerciais = {item["nome"] for item in cliente.get("/paleta/swatches").json()["items"]}
    assert "Vermelho" in nomes_comerciais
    tons = cliente.get("/paleta/swatches", params={"modo": "marketing"}).json()
    assert len(tons["items"]) > 12
    assert cliente.get("/imagens/999999").status_code == 404


def test_semelhantes_nao_inclui_a_origem(tmp_path: Path) -> None:
    cliente, _, imagem_id = _cliente(tmp_path)

    resposta = cliente.get(f"/imagens/{imagem_id}/semelhantes")

    assert resposta.status_code == 200
    assert resposta.json()["items"] == []


def test_api_token_protege_todas_as_rotas(tmp_path: Path) -> None:
    cliente, _, _ = _cliente(tmp_path)
    db = tmp_path / "catalogo.db"
    protegido = TestClient(create_app(db, api_token="token-de-teste"))

    assert protegido.get("/health").status_code == 401
    autorizado = protegido.get("/health", headers={"Authorization": "Bearer token-de-teste"})
    assert autorizado.status_code == 200
