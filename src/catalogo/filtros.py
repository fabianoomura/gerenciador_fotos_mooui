"""Construcao compartilhada das clausulas SQL de filtro (API e busca hibrida).

Regras do contrato V2:
- valores repetidos do mesmo filtro combinam com OR;
- filtros diferentes combinam com AND;
- valores prefixados com "!" negam (ex.: pessoa_tipo=!modelo);
- possui_modelo=true significa exatamente pessoa_tipo='modelo';
- possui_pessoa e' tri-estado no banco (1/0/NULL=desconhecido); o filtro
  booleano casa apenas com valores confirmados.
"""

from __future__ import annotations

CAMPOS_COLUNA = {
    "ano",
    "tipo",
    "colecao",
    "categoria",
    "pessoa",
    "pessoa_tipo",
    "ambiente_tipo",
    "ambiente_tema",
    "drop_tema",
    "formato_foto",
    "variante",
    "orientacao",
    "direitos_uso_status",
}
CAMPOS_CORES = {"cor": "cores_comerciais_json", "tom": "cores_marketing_json"}
CAMPOS_BOOL = {"possui_pessoa", "possui_modelo"}
CAMPOS_FILTRO = CAMPOS_COLUNA | set(CAMPOS_CORES) | CAMPOS_BOOL

VALORES_VALIDOS = {
    "orientacao": {"vertical", "horizontal", "square"},
    "direitos_uso_status": {"approved", "restricted", "unknown"},
}

_CORES_EXISTS = (
    "EXISTS (SELECT 1 FROM json_each(imagens.{coluna}) "
    "WHERE json_extract(value, '$.nome') IN ({marcadores}))"
)


def interpretar_bool(valor: object) -> bool:
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in {"true", "1", "sim"}:
        return True
    if texto in {"false", "0", "nao", "não"}:
        return False
    raise ValueError(f"Valor booleano invalido: {valor!r} (use true ou false)")


def _como_lista(valor: object) -> list[object]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple, set)):
        return [item for item in valor if item is not None]
    return [valor]


def _separar_negativos(valores: list[object]) -> tuple[list[object], list[str]]:
    positivos: list[object] = []
    negativos: list[str] = []
    for valor in valores:
        if isinstance(valor, str) and valor.startswith("!"):
            negativos.append(valor[1:])
        else:
            positivos.append(valor)
    return positivos, negativos


def construir_filtros_sql(filtros: dict[str, object]) -> tuple[list[str], list[object]]:
    """Retorna clausulas WHERE (uma por filtro) e a lista de parametros.

    Levanta ValueError para valores invalidos; chaves fora de CAMPOS_FILTRO
    sao ignoradas aqui (a API valida e rejeita antes com 422).
    """

    where: list[str] = []
    params: list[object] = []
    for campo, valor in filtros.items():
        valores = _como_lista(valor)
        if not valores or campo not in CAMPOS_FILTRO:
            continue
        if campo in CAMPOS_BOOL:
            ligado = interpretar_bool(valores[-1])
            if campo == "possui_modelo":
                where.append(
                    "pessoa_tipo = 'modelo'"
                    if ligado
                    else "(pessoa_tipo IS NULL OR pessoa_tipo != 'modelo')"
                )
            else:
                where.append("possui_pessoa = ?")
                params.append(1 if ligado else 0)
            continue
        positivos, negativos = _separar_negativos(valores)
        validos = VALORES_VALIDOS.get(campo)
        if validos:
            invalidos = [str(v) for v in positivos + negativos if str(v) not in validos]
            if invalidos:
                raise ValueError(
                    f"Valores invalidos para {campo}: {', '.join(invalidos)} "
                    f"(validos: {', '.join(sorted(validos))})"
                )
        if campo in CAMPOS_CORES:
            coluna = CAMPOS_CORES[campo]
            if positivos:
                marcadores = ",".join("?" for _ in positivos)
                where.append(_CORES_EXISTS.format(coluna=coluna, marcadores=marcadores))
                params.extend(positivos)
            if negativos:
                marcadores = ",".join("?" for _ in negativos)
                where.append("NOT " + _CORES_EXISTS.format(coluna=coluna, marcadores=marcadores))
                params.extend(negativos)
            continue
        if positivos:
            where.append(f"{campo} IN ({','.join('?' for _ in positivos)})")
            params.extend(positivos)
        if negativos:
            where.append(
                f"({campo} IS NULL OR {campo} NOT IN ({','.join('?' for _ in negativos)}))"
            )
            params.extend(negativos)
    return where, params
