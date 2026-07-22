"""Testes da extracao de cores dominantes e distancia perceptual."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from catalogo.palette import (
    delta_e,
    extrair_paleta,
    extrair_paleta_produto,
    simplificar_cores,
)


def test_extrai_cores_com_proporcao(tmp_path: Path) -> None:
    path = tmp_path / "cores.png"
    imagem = Image.new("RGB", (4, 1))
    imagem.putdata([(255, 0, 0), (255, 0, 0), (255, 0, 0), (0, 0, 255)])
    imagem.save(path)

    paleta = extrair_paleta(path, k=2)

    assert paleta[0]["hex"] == "#FF0000"
    assert paleta[0]["proporcao"] == 0.75
    assert {item["hex"] for item in paleta} == {"#FF0000", "#0000FF"}


def test_remove_transparencia_total(tmp_path: Path) -> None:
    path = tmp_path / "transparente.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(path)

    assert extrair_paleta(path, k=5) == []


def test_paleta_produto_remove_fundo_e_preserva_branco_interno() -> None:
    imagem = Image.new("RGB", (100, 100), "#E8E4DC")
    for y in range(20, 80):
        for x in range(20, 80):
            imagem.putpixel((x, y), (46, 132, 72) if x < 50 else (250, 250, 247))

    paleta = extrair_paleta_produto(imagem, k=3)

    hexes = {item["hex"] for item in paleta}
    assert "#E8E4DC" not in hexes
    assert "#2E8448" in hexes
    assert "#FAFAF7" in hexes


def test_paleta_produto_nao_apaga_imagem_que_preenche_o_quadro() -> None:
    imagem = Image.new("RGB", (40, 40), "#D94841")

    assert extrair_paleta_produto(imagem, k=3) == extrair_paleta(imagem, k=3)


def test_delta_e_distingue_cores_proximas_e_distantes() -> None:
    assert delta_e("#FF0000", "#FE0101") < delta_e("#FF0000", "#0000FF")
    assert delta_e("#FFFFFF", "#FFFFFF") == 0


def test_simplifica_tonalidades_em_cores_comerciais() -> None:
    paleta = [
        {"hex": "#3E7E4F", "proporcao": 0.45},
        {"hex": "#6FA36E", "proporcao": 0.20},
        {"hex": "#FAFAF5", "proporcao": 0.33},
        {"hex": "#D94841", "proporcao": 0.02},
    ]
    referencias = [
        {"nome": "Verde", "hex": "#5B8C5A"},
        {"nome": "Branco", "hex": "#F5F2E8"},
        {"nome": "Vermelho", "hex": "#D94841"},
    ]

    cores = simplificar_cores(paleta, referencias, max_cores=3, min_proporcao=0.06)

    assert [cor["nome"] for cor in cores] == ["Verde", "Branco"]
    assert cores[0]["proporcao"] == 0.65
    assert "/".join(cor["nome"] for cor in cores) == "Verde/Branco"
