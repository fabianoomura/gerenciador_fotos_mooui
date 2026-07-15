"""Testes do indexador incremental de metadados (sem abrir imagens)."""

from __future__ import annotations

from pathlib import Path

from catalogo.db import connect
from catalogo.indexer import indexar_metadados


def _touch(path: Path, conteudo: bytes = b"imagem") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(conteudo)


def test_indexa_metadata_pendencias_e_proxy(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    original = raiz / "2026" / "COLECAO 2026 - PRODUTOS" / "BONECAS" / "boneca-1.jpg"
    proxy = original.parent / "REDUZIDAS" / original.name
    _touch(original)
    _touch(proxy, b"proxy")
    db = tmp_path / "catalogo.db"

    resumo = indexar_metadados(db, raiz, verificar_readonly=False)

    assert resumo.novos == 1
    assert resumo.ignorados_nao_imagem == 0
    conn = connect(db)
    try:
        imagem = conn.execute("SELECT * FROM imagens").fetchone()
        assert imagem["ano"] == 2026
        assert imagem["categoria"] == "bonecas"
        assert imagem["reduzida_path"] == str(proxy)
        assert conn.execute("SELECT COUNT(*) FROM imagens").fetchone()[0] == 1
    finally:
        conn.close()


def test_reexecucao_sem_mudancas_e_idempotente(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    _touch(raiz / "2015" / "foto.jpg")
    db = tmp_path / "catalogo.db"

    primeiro = indexar_metadados(db, raiz, verificar_readonly=False)
    segundo = indexar_metadados(db, raiz, verificar_readonly=False)

    assert primeiro.novos == 1
    assert segundo.novos == 0
    assert segundo.alterados == 0


def test_marca_como_removido_sem_apagar_registro(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2015" / "foto.jpg"
    _touch(foto)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)
    foto.unlink()

    resumo = indexar_metadados(db, raiz, verificar_readonly=False)

    assert resumo.removidos == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT status FROM imagens").fetchone()["status"] == "removido"
    finally:
        conn.close()


def test_reprocessar_atualiza_parser_sem_alterar_arquivo(tmp_path: Path) -> None:
    raiz = tmp_path / "PHOTO LIBRARY"
    foto = raiz / "2015" / "foto.jpg"
    _touch(foto)
    db = tmp_path / "catalogo.db"
    indexar_metadados(db, raiz, verificar_readonly=False)

    resumo = indexar_metadados(db, raiz, verificar_readonly=False, reprocessar=True)

    assert resumo.novos == 0
    assert resumo.alterados == 1
