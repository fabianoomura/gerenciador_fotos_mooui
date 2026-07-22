"""Testes de sinonimos e do pool de candidatos da busca textual."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from catalogo.db import connect
from catalogo.indexer import indexar_metadados
from catalogo.search import buscar_hibrida
from catalogo.sinonimos import carregar_grupos, expandir_tokens
from catalogo.visual import processar_visuais


class FakeImageEmbedder:
    def encode_images(self, imagens):
        # embedding distinto por imagem para nao empatar o ranking vetorial
        saida = []
        for i, _ in enumerate(imagens):
            vetor = [0.0] * 512
            vetor[i % 512] = 1.0
            saida.append(vetor)
        return saida


class FakeTextEmbedder:
    def encode_text(self, texto: str):
        return [0.0] * 512  # neutro: forca a busca a depender do FTS/sinonimos


def _acervo(tmp_path: Path):
    raiz = tmp_path / "PHOTO LIBRARY"
    fotos = {
        "abajur": raiz / "2025" / "COLECAO 2025 - PRODUTOS" / "ABAJUR" / "abajur-listrado.png",
        "organizador": (
            raiz / "2025" / "COLECAO 2025 - PRODUTOS" / "BAIXA" / "CAIXA ORGANIZADORA"
            / "caixa-organizadora-nuvem.png"
        ),
        "edredom": (
            raiz / "2025" / "COLECAO 2025 - PRODUTOS" / "CAPA DE EDREDOM"
            / "capa-de-edredom-casal.png"
        ),
        "tenda": raiz / "2025" / "COLECAO 2025 - PRODUTOS" / "TENDA" / "tenda-infantil.png",
        "outra": raiz / "2025" / "COLECAO 2025 - ENSAIOS" / "PRAIA" / "ensaio-praia.png",
    }
    for path in fotos.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 3), "blue").save(path)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    processar_visuais(db, embedder=FakeImageEmbedder())
    return db, fotos


def _busca(db, texto):
    return buscar_hibrida(db, texto, embedder=FakeTextEmbedder(), limit=20)


def _paths(resultados):
    return {r["path"] for r in resultados}


def test_expandir_tokens_gera_equivalentes(tmp_path: Path) -> None:
    db, _ = _acervo(tmp_path)
    conn = connect(db)
    try:
        grupos = carregar_grupos(conn)
    finally:
        conn.close()
    assert "abajur" in expandir_tokens("luminaria de mesa", grupos)
    assert "edredom" in expandir_tokens("duvet casal", grupos)
    assert "tenda" in expandir_tokens("cabana infantil", grupos)
    assert "organizador" in expandir_tokens("porta treco", grupos)
    # consulta sem sinonimo conhecido nao expande
    assert expandir_tokens("quarto colorido", grupos) == set()


def test_sinonimo_ranqueia_termo_canonico_no_topo(tmp_path: Path) -> None:
    # Embedder de texto neutro: quem chega ao topo veio do FTS + sinonimo.
    db, fotos = _acervo(tmp_path)
    assert _busca(db, "luminaria")[0]["path"] == str(fotos["abajur"])
    assert _busca(db, "duvet")[0]["path"] == str(fotos["edredom"])
    assert _busca(db, "cabana")[0]["path"] == str(fotos["tenda"])
    assert _busca(db, "porta treco")[0]["path"] == str(fotos["organizador"])


def test_plural_e_variacao_encontram(tmp_path: Path) -> None:
    db, fotos = _acervo(tmp_path)
    # "caixa organizadora" (singular) deve achar a pasta "CAIXA ORGANIZADORA"
    assert _busca(db, "caixa organizadora")[0]["path"] == str(fotos["organizador"])
    assert _busca(db, "organizador")[0]["path"] == str(fotos["organizador"])


def test_pool_nao_depende_de_filtro_inferido(tmp_path: Path) -> None:
    # Antes, sem filtro inferido, a busca ranqueava um lote arbitrario e o item
    # pelo nome nao subia. Agora o proprio match textual dirige o topo.
    db, fotos = _acervo(tmp_path)
    assert _busca(db, "abajur")[0]["path"] == str(fotos["abajur"])


def test_filtro_sem_correspondencia_retorna_vazio(tmp_path: Path) -> None:
    db, _ = _acervo(tmp_path)
    assert buscar_hibrida(
        db, "abajur", embedder=FakeTextEmbedder(), tipo="inexistente"
    ) == []
