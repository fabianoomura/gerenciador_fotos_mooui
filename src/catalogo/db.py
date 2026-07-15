"""Conexao ao SQLite e bootstrap do schema."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_RESOURCE = "schema.sql"
SEEDS_RESOURCE = "seeds.sql"


def _try_load_vec_extension(conn: sqlite3.Connection) -> bool:
    """Carrega a extensao sqlite-vec, se disponivel.

    Retorna True em sucesso. Em ambientes sem sqlite-vec instalado (dev inicial,
    testes do parser), retorna False — o schema tem CREATE VIRTUAL TABLE vec_imagens
    que falha sem a extensao, entao esse CREATE fica opcional (aplicado depois).
    """
    try:
        conn.enable_load_extension(True)
    except AttributeError:
        return False
    try:
        import sqlite_vec  # type: ignore[import-untyped]
    except ImportError:
        return False
    sqlite_vec.load(conn)
    return True


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _try_load_vec_extension(conn)
    return conn


def _read_sql(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def bootstrap(db_path: Path | str, *, with_seeds: bool = True) -> None:
    """Cria o banco a partir de schema.sql e (opcional) carrega seeds.sql.

    Idempotente: schema usa CREATE IF NOT EXISTS, seeds usam INSERT OR IGNORE.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        vec_ok = _try_load_vec_extension(conn)
        _migrate_existing_schema(conn)
        schema_sql = _read_sql(SCHEMA_RESOURCE)
        if not vec_ok:
            schema_sql = _strip_vec_table(schema_sql)
        conn.executescript(schema_sql)
        if with_seeds:
            conn.executescript(_read_sql(SEEDS_RESOURCE))
        conn.commit()
    finally:
        conn.close()


def _migrate_existing_schema(conn: sqlite3.Connection) -> None:
    """Aplica adicoes simples antes dos indices do schema em bancos existentes."""

    tabelas = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for tabela in ("imagens", "vocab_pessoas"):
        if tabela not in tabelas:
            continue
        colunas = {row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})")}
        if "pessoa_tipo" not in colunas:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN pessoa_tipo TEXT")
        if tabela == "imagens" and "formato_foto" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN formato_foto TEXT")
        if tabela == "imagens" and "variante" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN variante TEXT")
        if tabela == "imagens" and "visual_status" not in colunas:
            conn.execute(
                "ALTER TABLE imagens ADD COLUMN visual_status TEXT NOT NULL DEFAULT 'pendente'"
            )
        if tabela == "imagens" and "visual_erro" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN visual_erro TEXT")
        if tabela == "imagens" and "thumb_path" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN thumb_path TEXT")
        if tabela == "imagens" and "cores_comerciais_json" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN cores_comerciais_json TEXT")
        if tabela == "imagens" and "cores_marketing_json" not in colunas:
            conn.execute("ALTER TABLE imagens ADD COLUMN cores_marketing_json TEXT")


def _strip_vec_table(sql: str) -> str:
    """Remove o CREATE VIRTUAL TABLE vec_imagens quando sqlite-vec nao esta instalado.

    Permite bootstrap em ambiente de dev sem a extensao (ex.: rodar testes do parser).
    """
    start_marker = "CREATE VIRTUAL TABLE IF NOT EXISTS vec_imagens"
    idx = sql.find(start_marker)
    if idx < 0:
        return sql
    end = sql.find(";", idx)
    if end < 0:
        return sql[:idx]
    return sql[:idx] + sql[end + 1 :]
