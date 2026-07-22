"""Testes do processamento visual incremental com embedder falso."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from catalogo.db import connect
from catalogo.indexer import indexar_metadados
from catalogo.visual import processar_visuais


class FakeEmbedder:
    def encode_images(self, imagens):
        return [[1.0] + [0.0] * 511 for _ in imagens]


def test_processa_paleta_e_embedding(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2026" / "COLECAO 2026 - PRODUTOS" / "BONECAS" / "foto.png"
    foto.parent.mkdir(parents=True)
    Image.new("RGB", (4, 4), "red").save(foto)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    thumbs = tmp_path / "thumbs"
    conn = connect(db)
    try:
        conn.execute("UPDATE config SET valor=? WHERE chave='thumbs_dir'", (str(thumbs),))
        conn.commit()
    finally:
        conn.close()

    resumo = processar_visuais(db, embedder=FakeEmbedder(), batch_size=2)

    assert resumo.processadas == 1
    assert resumo.erros == 0
    conn = connect(db)
    try:
        imagem = conn.execute(
            """
            SELECT id, paleta_json, paleta_produto_json, cores_comerciais_json,
                   cores_marketing_json, visual_status, thumb_path
            FROM imagens
            """
        ).fetchone()
        assert imagem["visual_status"] == "ok"
        assert '"#FF0000"' in imagem["paleta_json"]
        assert '"#FF0000"' in imagem["paleta_produto_json"]
        assert Path(imagem["thumb_path"]).is_file()
        assert '"Vermelho"' in imagem["cores_comerciais_json"]
        assert '"Vermelho"' in imagem["cores_marketing_json"]
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM vec_imagens WHERE rowid = ?", (imagem["id"],)
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_imagem_corrompida_registra_erro_e_segue(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2015" / "quebrada.jpg"
    foto.parent.mkdir(parents=True)
    foto.write_bytes(b"nao e imagem")
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    conn = connect(db)
    try:
        conn.execute(
            "UPDATE config SET valor=? WHERE chave='thumbs_dir'", (str(tmp_path / "thumbs"),)
        )
        conn.commit()
    finally:
        conn.close()

    resumo = processar_visuais(db, embedder=FakeEmbedder())

    assert resumo.erros == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT visual_status FROM imagens").fetchone()[0] == "erro"
    finally:
        conn.close()
