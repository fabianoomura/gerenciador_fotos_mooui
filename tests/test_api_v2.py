"""Testes do contrato V2: filtros estruturados, capacidades e rejeicao de params."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from catalogo.api import create_app
from catalogo.db import connect
from catalogo.indexer import calcular_orientacao, indexar_metadados
from catalogo.search import buscar_hibrida
from catalogo.visual import processar_visuais


class FakeImageEmbedder:
    def encode_images(self, imagens):
        return [[1.0] + [0.0] * 511 for _ in imagens]


class FakeTextEmbedder:
    def encode_text(self, texto: str):
        return [1.0] + [0.0] * 511


def _acervo(tmp_path: Path) -> tuple[TestClient, Path]:
    """Tres fotos: produto square, influenciador horizontal, modelo vertical."""

    raiz = tmp_path / "PHOTO LIBRARY"
    produto = raiz / "2026" / "COLECAO 2026 - PRODUTOS" / "BONECAS" / "produto.png"
    influ = (
        raiz
        / "2026"
        / "COLECAO 2026 - INFLUENCIADORES"
        / "NACIONAL"
        / "QUARTO - CLARA SOUZA (LUCAS)"
        / "influ.png"
    )
    modelo = raiz / "2026" / "COLECAO 2026 - ENSAIOS" / "PRAIA" / "modelo.png"
    for path, tamanho in ((produto, (3, 3)), (influ, (4, 2)), (modelo, (2, 4))):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", tamanho, "blue").save(path)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    conn = connect(db)
    try:
        conn.execute(
            "UPDATE config SET valor=? WHERE chave='thumbs_dir'", (str(tmp_path / "thumbs"),)
        )
        # papel de modelo vem de revisao humana/vocabulario, nunca do tipo ensaio
        conn.execute(
            "UPDATE imagens SET pessoa='maria exemplo', pessoa_tipo='modelo', "
            "possui_pessoa=1 WHERE path=?",
            (str(modelo),),
        )
        conn.commit()
    finally:
        conn.close()
    processar_visuais(db, embedder=FakeImageEmbedder())

    def searcher(texto, **filtros):
        return buscar_hibrida(db, texto, embedder=FakeTextEmbedder(), **filtros)

    return TestClient(create_app(db, searcher=searcher)), db


def test_calcular_orientacao() -> None:
    assert calcular_orientacao(2000, 1000) == "horizontal"
    assert calcular_orientacao(1000, 2000) == "vertical"
    assert calcular_orientacao(1000, 1000) == "square"
    assert calcular_orientacao(1000, 1040) == "square"  # proximo de 1:1
    assert calcular_orientacao(1000, 1200) == "vertical"
    assert calcular_orientacao(None, 1000) is None
    assert calcular_orientacao(0, 0) is None


def test_indexacao_grava_dimensoes(tmp_path: Path) -> None:
    _, db = _acervo(tmp_path)
    conn = connect(db)
    try:
        rows = {
            row["nome_arquivo"]: row
            for row in conn.execute(
                "SELECT nome_arquivo, largura, altura, orientacao, possui_pessoa, "
                "direitos_uso_status FROM imagens"
            )
        }
    finally:
        conn.close()
    assert (rows["produto.png"]["largura"], rows["produto.png"]["altura"]) == (3, 3)
    assert rows["produto.png"]["orientacao"] == "square"
    assert rows["influ.png"]["orientacao"] == "horizontal"
    assert rows["modelo.png"]["orientacao"] == "vertical"
    # evidencia de pessoa no path -> 1; produto sem evidencia -> NULL (desconhecido)
    assert rows["influ.png"]["possui_pessoa"] == 1
    assert rows["produto.png"]["possui_pessoa"] is None
    # direitos de uso nunca sao inferidos: nasce unknown ate revisao humana
    assert all(row["direitos_uso_status"] == "unknown" for row in rows.values())


def test_possui_modelo_true_retorna_somente_modelos(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    dados = cliente.get("/busca", params={"possui_modelo": "true"}).json()
    assert [item["pessoa_tipo"] for item in dados["items"]] == ["modelo"]
    assert dados["applied_filters"] == {"possui_modelo": ["true"]}


def test_possui_modelo_false_exclui_modelos(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    dados = cliente.get("/busca", params={"possui_modelo": "false"}).json()
    assert len(dados["items"]) == 2
    assert all(item["pessoa_tipo"] != "modelo" for item in dados["items"])


def test_possui_pessoa_e_tri_estado(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    com_pessoa = cliente.get("/busca", params={"possui_pessoa": "true"}).json()
    assert {item["nome_arquivo"] for item in com_pessoa["items"]} == {"influ.png", "modelo.png"}
    # produto.png tem possui_pessoa NULL (desconhecido): nao casa com false
    sem_pessoa = cliente.get("/busca", params={"possui_pessoa": "false"}).json()
    assert sem_pessoa["items"] == []


def test_q_combinado_com_filtros_restringe_antes_do_ranking(tmp_path: Path) -> None:
    cliente, db = _acervo(tmp_path)
    # os tres embeddings sao identicos: sem o filtro, o ranking vetorial traria todos
    todos = buscar_hibrida(db, "quarto azul", embedder=FakeTextEmbedder())
    assert len(todos) == 3
    so_verticais = buscar_hibrida(
        db, "quarto azul", embedder=FakeTextEmbedder(), orientacao="vertical"
    )
    assert [item["orientacao"] for item in so_verticais] == ["vertical"]
    resposta = cliente.get("/busca", params={"q": "quarto azul", "orientacao": "vertical"})
    assert [item["orientacao"] for item in resposta.json()["items"]] == ["vertical"]


def test_or_dentro_do_mesmo_filtro(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    dados = cliente.get("/busca?orientacao=vertical&orientacao=square").json()
    assert {item["orientacao"] for item in dados["items"]} == {"vertical", "square"}
    assert dados["applied_filters"]["orientacao"] == ["vertical", "square"]


def test_and_entre_filtros_diferentes(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    combinado = cliente.get("/busca", params={"tipo": "produtos", "orientacao": "square"}).json()
    assert len(combinado["items"]) == 1
    vazio = cliente.get("/busca", params={"tipo": "produtos", "orientacao": "vertical"}).json()
    assert vazio["items"] == []
    assert vazio["total"] == 0


def test_filtro_desconhecido_retorna_422(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    resposta = cliente.get("/busca", params={"tema": "tropical"})
    assert resposta.status_code == 422
    detalhe = resposta.json()["detail"]
    assert detalhe["filtros_desconhecidos"] == ["tema"]
    assert "orientacao" in detalhe["filtros_validos"]


@pytest.mark.parametrize(
    "params",
    [{"orientacao": "diagonal"}, {"possui_modelo": "talvez"}, {"direitos_uso_status": "maybe"}],
)
def test_valores_invalidos_retornam_422(tmp_path: Path, params: dict[str, str]) -> None:
    cliente, _ = _acervo(tmp_path)
    assert cliente.get("/busca", params=params).status_code == 422


def test_filtro_negativo(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    dados = cliente.get("/busca", params={"pessoa_tipo": "!modelo"}).json()
    assert len(dados["items"]) == 2
    assert all(item["pessoa_tipo"] != "modelo" for item in dados["items"])


def test_capabilities(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    dados = cliente.get("/capabilities").json()
    assert dados["api_version"] == "2"
    assert dados["search_mode"] == ["metadata", "fts", "vector", "hybrid"]
    assert dados["filters"]["orientacao"] == ["horizontal", "square", "vertical"]
    assert dados["filters"]["possui_modelo"] == "boolean"
    assert dados["filters"]["direitos_uso_status"] == ["approved", "restricted", "unknown"]
    assert dados["supports_negative_filters"] is True


def test_api_permanece_somente_leitura(tmp_path: Path) -> None:
    cliente, _ = _acervo(tmp_path)
    rotas = {
        rota.path: rota.methods
        for rota in cliente.app.routes
        if getattr(rota, "methods", None) and rota.path not in ("/openapi.json", "/docs",
                                                                 "/docs/oauth2-redirect", "/redoc")
    }
    # nenhuma rota de escrita: apenas GET (+HEAD implicito) e o POST de busca por imagem
    for path, metodos in rotas.items():
        extras = set(metodos) - {"GET", "HEAD"}
        assert extras <= {"POST"}, f"metodo inesperado em {path}: {metodos}"
        if "POST" in extras:
            assert path == "/busca/por-imagem"


def test_originais_intactos_apos_uso(tmp_path: Path) -> None:
    cliente, db = _acervo(tmp_path)
    raiz = tmp_path / "PHOTO LIBRARY"
    antes = {path: path.stat().st_mtime for path in raiz.rglob("*.png")}
    cliente.get("/busca", params={"orientacao": "vertical"})
    cliente.get("/capabilities")
    conn = connect(db)
    try:
        imagem_id = conn.execute("SELECT id FROM imagens LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    cliente.get(f"/imagens/{imagem_id}/thumb")
    cliente.get(f"/imagens/{imagem_id}/download")
    depois = {path: path.stat().st_mtime for path in raiz.rglob("*.png")}
    assert antes == depois
