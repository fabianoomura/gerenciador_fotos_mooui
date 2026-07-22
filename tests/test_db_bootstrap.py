"""Sanity check do bootstrap do banco (schema + seeds)."""

from __future__ import annotations

import json
from pathlib import Path

from catalogo.db import bootstrap, connect


def test_bootstrap_cria_tabelas_essenciais(tmp_path: Path) -> None:
    db = tmp_path / "catalogo.db"
    bootstrap(db)

    conn = connect(db)
    try:
        tabelas = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    finally:
        conn.close()

    esperado = {
        "imagens",
        "imagens_fts",
        "vocab_tipo",
        "vocab_pessoas",
        "config",
        "nao_classificados",
        "scan_runs",
    }
    faltando = esperado - tabelas
    assert not faltando, f"Tabelas ausentes: {faltando}"


def test_seeds_populam_vocab_e_config(tmp_path: Path) -> None:
    db = tmp_path / "catalogo.db"
    bootstrap(db)

    conn = connect(db)
    try:
        tipos = dict(conn.execute("SELECT termo, tipo FROM vocab_tipo").fetchall())
        modelo = conn.execute(
            "SELECT valor FROM config WHERE chave = 'modelo_embedding'"
        ).fetchone()["valor"]
        exts_raw = conn.execute(
            "SELECT valor FROM config WHERE chave = 'extensoes_aceitas'"
        ).fetchone()["valor"]
        colunas_imagens = {
            row["name"] for row in conn.execute("PRAGMA table_info(imagens)").fetchall()
        }
        colunas_pessoas = {
            row["name"] for row in conn.execute("PRAGMA table_info(vocab_pessoas)").fetchall()
        }
    finally:
        conn.close()

    assert tipos["ensaios"] == "ensaio"
    assert tipos["quartinhos"] == "quartinhos"
    assert tipos["produtos"] == "produtos"
    assert tipos["arquitetos"] == "arquitetos"
    assert tipos["influenciadores"] == "influenciadores"
    # Tematicas ficam para v1.1 (parser v1 so estrutura pastas de ano):
    assert "insta" not in tipos
    assert "clip-ViT-B-32-multilingual-v1" in modelo
    assert set(json.loads(exts_raw)) == {".jpg", ".jpeg", ".png", ".webp"}
    assert "pessoa_tipo" in colunas_imagens
    assert "formato_foto" in colunas_imagens
    assert "variante" in colunas_imagens
    assert "thumb_path" in colunas_imagens
    assert "cores_comerciais_json" in colunas_imagens
    assert "cores_marketing_json" in colunas_imagens
    assert "paleta_produto_json" in colunas_imagens
    assert "pessoa_tipo" in colunas_pessoas


def test_bootstrap_e_idempotente(tmp_path: Path) -> None:
    db = tmp_path / "catalogo.db"
    bootstrap(db)
    bootstrap(db)  # segunda vez nao deve quebrar nem duplicar

    conn = connect(db)
    try:
        n_tipo = conn.execute("SELECT COUNT(*) FROM vocab_tipo").fetchone()[0]
        n_config = conn.execute("SELECT COUNT(*) FROM config").fetchone()[0]
    finally:
        conn.close()

    assert n_tipo > 0
    assert n_config > 0


def test_fts_reflete_insert(tmp_path: Path) -> None:
    db = tmp_path / "catalogo.db"
    bootstrap(db)

    conn = connect(db)
    try:
        conn.execute(
            """
            INSERT INTO imagens (path, path_raw, nome_arquivo, mtime, tamanho_bytes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "/mnt/photo-library/x/quarto-infantil-cachorros.jpg",
                "2026 colecao quartinhos quarto infantil cachorrinhos",
                "quarto-infantil-cachorros.jpg",
                1_700_000_000.0,
                1234,
            ),
        )
        conn.commit()
        hits = conn.execute(
            "SELECT rowid FROM imagens_fts WHERE imagens_fts MATCH 'cachorrinhos'"
        ).fetchall()
    finally:
        conn.close()

    assert len(hits) == 1
