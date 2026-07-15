"""Teste da busca vetorial texto->imagem."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from catalogo.indexer import indexar_metadados
from catalogo.search import buscar_hibrida, buscar_semantica
from catalogo.visual import processar_visuais


class FakeImageEmbedder:
    def encode_images(self, imagens):
        return [[1.0] + [0.0] * 511 for _ in imagens]


class FakeTextEmbedder:
    def encode_text(self, texto: str):
        return [1.0] + [0.0] * 511


def test_busca_semantica_retorna_metadata(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2026" / "COLECAO 2026 - QUARTINHOS" / "QUARTO INFANTIL CAES" / "foto.png"
    foto.parent.mkdir(parents=True)
    Image.new("RGB", (2, 2), "blue").save(foto)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    processar_visuais(db, embedder=FakeImageEmbedder())

    resultados = buscar_semantica(db, "quarto azul", embedder=FakeTextEmbedder(), limit=5)

    assert len(resultados) == 1
    assert resultados[0]["path"] == str(foto)
    assert resultados[0]["distancia"] == 0.0


def test_busca_hibrida_infere_pessoa_e_tipo(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    correta = (
        raiz
        / "2026"
        / "COLECAO 2026 - INFLUENCIADORES"
        / "NACIONAL"
        / "QUARTO - CLARA SOUZA (LUCAS)"
        / "foto.png"
    )
    outra = raiz / "2026" / "COLECAO 2026 - PRODUTOS" / "BONECAS" / "outra.png"
    for path in (correta, outra):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2, 2), "blue").save(path)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    processar_visuais(db, embedder=FakeImageEmbedder())

    resultados = buscar_hibrida(
        db,
        "quarto da influenciadora Clara Souza",
        embedder=FakeTextEmbedder(),
    )

    assert [item["path"] for item in resultados] == [str(correta)]
