"""Expansao da consulta textual por sinonimos de produto.

Os grupos vivem na tabela `sinonimos` (curada pelo administrador). Ao digitar
qualquer termo de um grupo, a busca tambem procura os demais termos daquele
grupo — assim "luminaria" encontra "abajur", "duvet" encontra "edredom" etc.

A expansao produz apenas tokens extras para o ramo OR do FTS; nunca adiciona
filtros rigidos (isso reduziria a cobertura). O ranking bm25 do FTS ja pondera
os tokens raros acima dos genericos.
"""

from __future__ import annotations

import re
import sqlite3

from catalogo.parser import normalizar_segmento

# Conectores sem valor discriminativo: nao viram token de expansao.
_TOKENS_GENERICOS = {"de", "com", "para", "da", "do", "dos", "das", "kit", "conjunto"}


def carregar_grupos(conn: sqlite3.Connection) -> list[frozenset[str]]:
    """Le a tabela `sinonimos` e devolve um grupo por conjunto de termos."""

    try:
        linhas = conn.execute("SELECT grupo, termo FROM sinonimos").fetchall()
    except sqlite3.OperationalError:
        return []  # banco antigo sem a tabela: expansao vira no-op
    grupos: dict[str, set[str]] = {}
    for linha in linhas:
        grupos.setdefault(linha[0], set()).add(linha[1])
    return [frozenset(termos) for termos in grupos.values()]


def _dispara(texto_norm: str, termo: str) -> bool:
    """Verdadeiro se `termo` aparece como palavra (plural permitido) no texto."""

    return re.search(rf"(?<![a-z0-9]){re.escape(termo)}", texto_norm) is not None


def _tokens(termo: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", termo)
        if len(token) >= 3 and token not in _TOKENS_GENERICOS
    ]


def expandir_tokens(texto: str, grupos: list[frozenset[str]]) -> set[str]:
    """Tokens extras a somar ao ramo OR do FTS, a partir dos grupos disparados."""

    texto_norm = normalizar_segmento(texto)
    extras: set[str] = set()
    for termos in grupos:
        if any(_dispara(texto_norm, termo) for termo in termos):
            for termo in termos:
                extras.update(_tokens(termo))
    # Nao repete o que o usuario ja digitou (esses tokens ja entram na consulta).
    ja_digitados = set(_tokens(texto_norm))
    return extras - ja_digitados
