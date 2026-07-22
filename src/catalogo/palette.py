"""Paleta dominante e comparacao perceptual de cores."""

from __future__ import annotations

import math
from collections import deque
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

    return _quantizar_pixels(pixels, k)


def extrair_paleta_produto(
    fonte: Path | Image.Image,
    *,
    k: int = 5,
    max_size: int = 256,
    tolerancia_fundo: float = 38.0,
) -> list[dict[str, object]]:
    """Extrai cores do produto removendo apenas fundos uniformes ligados as bordas.

    A remocao so e aplicada quando pelo menos dois cantos concordam sobre a cor
    do fundo e a mascara ocupa uma fracao plausivel da imagem. Em fotos sem fundo
    de estudio confiavel, retorna a paleta integral.
    """

    if isinstance(fonte, Image.Image):
        imagem = fonte.convert("RGBA")
    else:
        with Image.open(fonte) as origem:
            imagem = origem.convert("RGBA")
    imagem.thumbnail((max_size, max_size))
    largura, altura = imagem.size
    if largura < 4 or altura < 4:
        return extrair_paleta(imagem, k=k, max_size=max_size)

    pixels = list(imagem.get_flattened_data())
    opacos = [pixel[:3] for pixel in pixels if pixel[3] > 0]
    if not opacos:
        return []

    referencias = _referencias_de_fundo(pixels, largura, altura, tolerancia_fundo)
    if not referencias:
        return _quantizar_pixels(opacos, k)

    fundo = _mascara_fundo(
        pixels,
        largura,
        altura,
        referencias,
        tolerancia_fundo,
    )
    cobertura = len(fundo) / len(opacos)
    if cobertura < 0.08 or cobertura > 0.92:
        return _quantizar_pixels(opacos, k)

    produto = [
        pixel[:3]
        for indice, pixel in enumerate(pixels)
        if pixel[3] > 0 and indice not in fundo
    ]
    return _quantizar_pixels(produto, k) if produto else _quantizar_pixels(opacos, k)


def _quantizar_pixels(
    pixels: list[tuple[int, int, int]],
    k: int,
) -> list[dict[str, object]]:
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


def _referencias_de_fundo(
    pixels: list[tuple[int, int, int, int]],
    largura: int,
    altura: int,
    tolerancia: float,
) -> list[tuple[int, int, int]]:
    lado = max(2, min(largura, altura) // 20)
    cantos = (
        (range(lado), range(lado)),
        (range(largura - lado, largura), range(lado)),
        (range(lado), range(altura - lado, altura)),
        (range(largura - lado, largura), range(altura - lado, altura)),
    )
    candidatos: list[tuple[int, int, int]] = []
    for xs, ys in cantos:
        amostra = [
            pixels[y * largura + x][:3]
            for y in ys
            for x in xs
            if pixels[y * largura + x][3] > 0
        ]
        if not amostra:
            continue
        mediana = tuple(sorted(canal)[len(canal) // 2] for canal in zip(*amostra, strict=True))
        desvio_medio = sum(_distancia_rgb(pixel, mediana) for pixel in amostra) / len(amostra)
        if desvio_medio <= tolerancia * 0.45:
            candidatos.append(mediana)  # type: ignore[arg-type]

    return [
        cor
        for cor in candidatos
        if sum(_distancia_rgb(cor, outra) <= tolerancia for outra in candidatos) >= 2
    ]


def _mascara_fundo(
    pixels: list[tuple[int, int, int, int]],
    largura: int,
    altura: int,
    referencias: list[tuple[int, int, int]],
    tolerancia: float,
) -> set[int]:
    def parece_fundo(indice: int) -> bool:
        pixel = pixels[indice]
        return pixel[3] > 0 and min(
            _distancia_rgb(pixel[:3], referencia) for referencia in referencias
        ) <= tolerancia

    borda = set(range(largura))
    borda.update(range((altura - 1) * largura, altura * largura))
    borda.update(y * largura for y in range(altura))
    borda.update(y * largura + largura - 1 for y in range(altura))
    fila = deque(indice for indice in borda if parece_fundo(indice))
    fundo = set(fila)
    while fila:
        indice = fila.popleft()
        x, y = indice % largura, indice // largura
        vizinhos = []
        if x > 0:
            vizinhos.append(indice - 1)
        if x + 1 < largura:
            vizinhos.append(indice + 1)
        if y > 0:
            vizinhos.append(indice - largura)
        if y + 1 < altura:
            vizinhos.append(indice + largura)
        for vizinho in vizinhos:
            if vizinho not in fundo and parece_fundo(vizinho):
                fundo.add(vizinho)
                fila.append(vizinho)
    return fundo


def _distancia_rgb(
    cor_a: tuple[int, int, int],
    cor_b: tuple[int, int, int],
) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(cor_a, cor_b, strict=True)))


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
