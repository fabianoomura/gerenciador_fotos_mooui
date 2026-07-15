"""Indexacao incremental de metadados, sem processamento visual pesado."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from catalogo.db import bootstrap, connect
from catalogo.parser import ParsedPath, parse_path
from catalogo.scanner import scan_tree, validar_mount_readonly


@dataclass(slots=True)
class IndexResult:
    novos: int = 0
    alterados: int = 0
    removidos: int = 0
    ignorados_nao_imagem: int = 0
    erros: int = 0


def indexar_metadados(
    db_path: Path,
    raiz: Path,
    *,
    verificar_readonly: bool = True,
    mounts_text: str | None = None,
    reprocessar: bool = False,
    recursivo: bool = True,
) -> IndexResult:
    """Varre um escopo, faz upsert dos metadados e registra a execucao."""

    if verificar_readonly:
        validar_mount_readonly(raiz, mounts_text=mounts_text)
    bootstrap(db_path)
    conn = connect(db_path)
    inicio = time.time()
    resumo = IndexResult()
    try:
        config = {
            row["chave"]: row["valor"] for row in conn.execute("SELECT chave, valor FROM config")
        }
        vocab_tipo = dict(conn.execute("SELECT termo, tipo FROM vocab_tipo"))
        extensoes = set(json.loads(config["extensoes_aceitas"]))
        scan = scan_tree(
            raiz,
            extensoes=extensoes,
            reduzidas_pasta_nome=config["reduzidas_pasta_nome"],
            segmentos_ignorados=set(json.loads(config["segmentos_ignorados"])),
            recursivo=recursivo,
        )
        resumo.ignorados_nao_imagem = scan.ignorados_nao_imagem
        vistos: set[str] = set()

        for item in scan.imagens:
            path_texto = str(item.path)
            vistos.add(path_texto)
            try:
                stat = item.path.stat()
                existente = conn.execute(
                    "SELECT id, mtime, tamanho_bytes, status FROM imagens WHERE path = ?",
                    (path_texto,),
                ).fetchone()
                if (
                    existente is not None
                    and existente["mtime"] == stat.st_mtime
                    and existente["tamanho_bytes"] == stat.st_size
                    and existente["status"] != "removido"
                    and not reprocessar
                ):
                    continue
                parsed = parse_path(path_texto, vocab_tipo=vocab_tipo)
                if item.reduzida_orfa:
                    parsed.path_raw += " reduzida orfa"
                    parsed.pendentes.append("reduzida orfa")
                    parsed.status = "parcial" if parsed.tipo else "nao_classificado"
                imagem_id = _upsert_imagem(
                    conn,
                    parsed,
                    mtime=stat.st_mtime,
                    tamanho=stat.st_size,
                    reduzida_path=str(item.reduzida_path) if item.reduzida_path else None,
                )
                _substituir_pendentes(conn, imagem_id, parsed.pendentes)
                _registrar_pessoa(conn, parsed)
                if existente is None:
                    resumo.novos += 1
                else:
                    resumo.alterados += 1
            except OSError:
                resumo.erros += 1

        prefixo = str(raiz).rstrip("/\\")
        ativos = conn.execute(
            "SELECT id, path FROM imagens WHERE path LIKE ? AND status != 'removido'",
            (f"{prefixo}%",),
        ).fetchall()
        for row in ativos:
            pertence_ao_escopo = recursivo or Path(row["path"]).parent == raiz
            if pertence_ao_escopo and row["path"] not in vistos:
                conn.execute(
                    "UPDATE imagens SET status = 'removido', atualizado_em = ? WHERE id = ?",
                    (time.time(), row["id"]),
                )
                resumo.removidos += 1

        fim = time.time()
        conn.execute(
            """
            INSERT INTO scan_runs
                (inicio, fim, novos, alterados, removidos, ignorados_nao_imagem, erros,
                 escopo_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inicio,
                fim,
                resumo.novos,
                resumo.alterados,
                resumo.removidos,
                resumo.ignorados_nao_imagem,
                resumo.erros,
                json.dumps([str(raiz)], ensure_ascii=False),
            ),
        )
        conn.commit()
        return resumo
    finally:
        conn.close()


def _upsert_imagem(
    conn,
    parsed: ParsedPath,
    *,
    mtime: float,
    tamanho: int,
    reduzida_path: str | None,
) -> int:
    valores = (
        parsed.path,
        parsed.path_raw,
        parsed.nome_arquivo,
        parsed.ano,
        parsed.tipo,
        parsed.colecao,
        parsed.categoria,
        parsed.drop_numero,
        parsed.drop_tema,
        parsed.pessoa,
        parsed.pessoa_tipo,
        parsed.formato_foto,
        parsed.variante,
        parsed.ambiente_tipo,
        parsed.ambiente_tema,
        parsed.slug_arquivo,
        reduzida_path,
        mtime,
        tamanho,
        parsed.status,
        time.time(),
    )
    conn.execute(
        """
        INSERT INTO imagens
            (path, path_raw, nome_arquivo, ano, tipo, colecao, categoria, drop_numero,
             drop_tema, pessoa, pessoa_tipo, formato_foto, variante, ambiente_tipo,
             ambiente_tema, slug_arquivo,
             reduzida_path, mtime, tamanho_bytes, status, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            path_raw=excluded.path_raw, nome_arquivo=excluded.nome_arquivo,
            ano=excluded.ano, tipo=excluded.tipo, colecao=excluded.colecao,
            categoria=excluded.categoria, drop_numero=excluded.drop_numero,
            drop_tema=excluded.drop_tema, pessoa=excluded.pessoa,
            pessoa_tipo=excluded.pessoa_tipo, ambiente_tipo=excluded.ambiente_tipo,
            formato_foto=excluded.formato_foto,
            variante=excluded.variante,
            ambiente_tema=excluded.ambiente_tema, slug_arquivo=excluded.slug_arquivo,
            reduzida_path=excluded.reduzida_path, mtime=excluded.mtime,
            tamanho_bytes=excluded.tamanho_bytes, status=excluded.status,
            atualizado_em=excluded.atualizado_em
        """,
        valores,
    )
    return conn.execute("SELECT id FROM imagens WHERE path = ?", (parsed.path,)).fetchone()["id"]


def _substituir_pendentes(conn, imagem_id: int, pendentes: list[str]) -> None:
    conn.execute("DELETE FROM nao_classificados WHERE imagem_id = ?", (imagem_id,))
    conn.executemany(
        "INSERT INTO nao_classificados (imagem_id, segmento_pendente, posicao) VALUES (?, ?, ?)",
        [(imagem_id, segmento, posicao) for posicao, segmento in enumerate(pendentes)],
    )


def _registrar_pessoa(conn, parsed: ParsedPath) -> None:
    if parsed.pessoa is None:
        return
    conn.execute(
        """
        INSERT INTO vocab_pessoas (termo, canonical, pessoa_tipo)
        VALUES (?, ?, ?)
        ON CONFLICT(termo) DO UPDATE SET
            pessoa_tipo=COALESCE(vocab_pessoas.pessoa_tipo, excluded.pessoa_tipo)
        """,
        (parsed.pessoa, parsed.pessoa, parsed.pessoa_tipo),
    )
