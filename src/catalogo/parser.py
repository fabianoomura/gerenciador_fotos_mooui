"""Parser deterministico dos caminhos do acervo de fotos."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath

from unidecode import unidecode


@dataclass(slots=True)
class ParsedPath:
    """Metadados que podem ser inferidos sem abrir a imagem."""

    path: str
    path_raw: str
    nome_arquivo: str
    slug_arquivo: str
    ano: int | None = None
    tipo: str | None = None
    colecao: str | None = None
    categoria: str | None = None
    pessoa: str | None = None
    pessoa_tipo: str | None = None
    formato_foto: str | None = None
    variante: str | None = None
    drop_numero: int | None = None
    drop_tema: str | None = None
    ambiente_tipo: str | None = None
    ambiente_tema: str | None = None
    status: str = "nao_classificado"
    pendentes: list[str] = field(default_factory=list)


def normalizar_segmento(valor: str) -> str:
    """Remove acentos, converte para minusculas e normaliza espacos."""

    return " ".join(unidecode(valor).lower().split())


def slug_do_arquivo(nome_arquivo: str) -> str:
    """Produz o slug pesquisavel, removendo extensao e sequencias de exportacao."""

    nome = re.sub(r"\.[^.]+$", "", nome_arquivo)
    nome = normalizar_segmento(nome).rstrip(". ")
    nome = re.sub(r"\s*\(\d+\)$", "", nome)
    nome = re.sub(r"(?:-\d+)?(?:_\d+_?)?$", "", nome)
    nome = re.sub(r"\s*-\s*", "-", nome)
    return nome.rstrip("-_. ")


def parse_path(path: str, *, vocab_tipo: dict[str, str]) -> ParsedPath:
    """Interpreta um path absoluto ou relativo e degrada segmentos desconhecidos."""

    partes = list(PurePath(path.replace("\\", "/")).parts)
    nome_arquivo = partes[-1]
    slug = slug_do_arquivo(nome_arquivo)
    segmentos = [normalizar_segmento(item) for item in partes[:-1]]

    inicio = next(
        (i for i, item in enumerate(segmentos) if re.fullmatch(r"20\d{2}(?: - ok)?", item)),
        None,
    )
    if inicio is None:
        # Sem ano, somente os segmentos abaixo da raiz conhecida interessam ao FTS.
        inicio = next(
            (i + 1 for i, item in enumerate(segmentos) if item == "mooui - fotos"),
            max(0, len(segmentos) - 2),
        )
        relativos = segmentos[inicio:]
        return ParsedPath(
            path=path,
            path_raw=" ".join([*relativos, slug]),
            nome_arquivo=nome_arquivo,
            slug_arquivo=slug,
            pendentes=relativos,
        )

    relativos = segmentos[inicio:]
    resultado = ParsedPath(
        path=path,
        path_raw=" ".join([*relativos, slug]),
        nome_arquivo=nome_arquivo,
        slug_arquivo=slug,
        ano=int(relativos[0][:4]),
    )

    espera_pessoa = False
    for segmento in relativos[1:]:
        if segmento == "crop":
            resultado.variante = "crop"
            continue
        colecao_tipo = re.fullmatch(r"(.+?)\s*-\s*(.+)", segmento)
        if colecao_tipo and colecao_tipo.group(2) in vocab_tipo:
            resultado.colecao = colecao_tipo.group(1)
            resultado.tipo = vocab_tipo[colecao_tipo.group(2)]
            espera_pessoa = resultado.tipo in {"ensaio", "arquitetos", "influenciadores"}
            continue

        if espera_pessoa:
            if resultado.tipo == "influenciadores" and segmento in {"nacional", "internacional"}:
                if segmento == "internacional":
                    resultado.formato_foto = "marketplace internacional"
                continue
            if resultado.tipo == "influenciadores":
                quarto_pessoa = re.fullmatch(r"quarto\s*-\s*(.+?)(?:\s*\((.+)\))?", segmento)
                if quarto_pessoa:
                    resultado.pessoa = quarto_pessoa.group(1)
                    resultado.pessoa_tipo = "influenciador"
                    resultado.ambiente_tipo = "quarto"
                    resultado.ambiente_tema = quarto_pessoa.group(2)
                    espera_pessoa = False
                    continue
            pessoa, separador, colecao = segmento.partition(" - ")
            resultado.pessoa = pessoa
            if resultado.tipo == "arquitetos":
                resultado.pessoa_tipo = "arquiteto"
            elif resultado.tipo == "influenciadores":
                resultado.pessoa_tipo = "influenciador"
            if separador:
                resultado.colecao = colecao
            espera_pessoa = False
            continue

        drop = re.fullmatch(r"drop\s+(\d+)\s*-\s*(.+)", segmento)
        if drop:
            resultado.drop_numero = int(drop.group(1))
            resultado.drop_tema = drop.group(2)
            continue

        quarto = re.fullmatch(r"quarto\s*-\s*(.+)", segmento)
        if quarto:
            resultado.ambiente_tipo = "quarto"
            resultado.ambiente_tema = quarto.group(1)
            continue

        quarto_infantil = re.fullmatch(r"quarto infantil\s+(.+)", segmento)
        if quarto_infantil:
            resultado.ambiente_tipo = "quarto infantil"
            resultado.ambiente_tema = quarto_infantil.group(1)
            continue

        if resultado.ambiente_tema is not None:
            resultado.ambiente_tema += f" > {segmento}"
            continue

        if resultado.tipo == "produtos" and resultado.categoria is None:
            resultado.categoria = segmento
            continue

        resultado.pendentes.append(segmento)

    if resultado.tipo is None:
        resultado.status = "nao_classificado"
    elif resultado.pendentes:
        resultado.status = "parcial"
    else:
        resultado.status = "ok"
    return resultado
