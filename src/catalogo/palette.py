"""Paleta dominante e comparacao perceptual de cores."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image


def extrair_paleta(
    fonte: Path | Image.Image,
    *,
    k: int = 5,
    max_size: int = 256,
) -> list[dict[str, object]]:
    """Extrai ate ``k`` cores dominantes com proporcao, sem alterar o arquivo."""

    if isinstance(fonte, Image.Image):
        imagem = fonte.convert("RGBA")
    else:
        with Image.open(fonte) as origem:
            imagem = origem.convert("RGBA")
    imagem.thumbnail((max_size, max_size))
    dados = imagem.tobytes()
    pixels = [tuple(dados[i : i + 3]) for i in range(0, len(dados), 4) if dados[i + 3] > 0]
    if not pixels:
        return []

    rgb = Image.new("RGB", (len(pixels), 1))
    rgb.putdata(pixels)
    quantizada = rgb.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    cores = quantizada.getcolors(maxcolors=k) or []
    paleta_rgb = quantizada.getpalette() or []
    total = sum(contagem for contagem, _ in cores)
    resultado = []
    for contagem, indice in sorted(cores, reverse=True):
        base = indice * 3
        cor = tuple(paleta_rgb[base : base + 3])
        resultado.append(
            {
                "hex": "#{:02X}{:02X}{:02X}".format(*cor),
                "proporcao": round(contagem / total, 6),
            }
        )
    return resultado


@lru_cache(maxsize=262144)
def delta_e(hex_a: str, hex_b: str) -> float:
    """Distancia CIE76 entre duas cores hexadecimais no espaco Lab."""

    lab_a = _rgb_para_lab(_hex_para_rgb(hex_a))
    lab_b = _rgb_para_lab(_hex_para_rgb(hex_b))
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab_a, lab_b, strict=True)))


def simplificar_cores(
    paleta: list[dict[str, object]],
    referencias: list[dict[str, str]],
    *,
    max_cores: int = 3,
    min_proporcao: float = 0.06,
) -> list[dict[str, object]]:
    """Agrupa tonalidades próximas em nomes comerciais estáveis."""

    agrupadas: dict[str, dict[str, object]] = {}
    for cor in paleta:
        proporcao = float(cor["proporcao"])
        if proporcao < min_proporcao:
            continue
        referencia = min(
            referencias,
            key=lambda item: delta_e(str(cor["hex"]), item["hex"]),
        )
        nome = referencia["nome"]
        atual = agrupadas.setdefault(
            nome,
            {"nome": nome, "hex": referencia["hex"], "proporcao": 0.0},
        )
        atual["proporcao"] = float(atual["proporcao"]) + proporcao

    resultado = sorted(
        agrupadas.values(),
        key=lambda item: float(item["proporcao"]),
        reverse=True,
    )[:max_cores]
    for item in resultado:
        item["proporcao"] = round(float(item["proporcao"]), 6)
    return resultado


@lru_cache(maxsize=8192)
def _hex_para_rgb(valor: str) -> tuple[int, int, int]:
    limpo = valor.lstrip("#")
    if len(limpo) != 6:
        raise ValueError(f"Cor hexadecimal invalida: {valor}")
    return tuple(int(limpo[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@lru_cache(maxsize=8192)
def _rgb_para_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    linear = []
    for canal in rgb:
        valor = canal / 255
        linear.append(valor / 12.92 if valor <= 0.04045 else ((valor + 0.055) / 1.055) ** 2.4)
    r, g, b = linear
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(valor: float) -> float:
        return valor ** (1 / 3) if valor > 0.008856 else 7.787 * valor + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)
