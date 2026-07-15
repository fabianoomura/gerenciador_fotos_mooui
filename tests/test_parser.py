"""Testes do parser determinístico de caminhos.

Casos cobertos:
- Ambiguidade 1: categoria (novo campo) em imagens dentro de PRODUTOS
- Ambiguidade 2: ambiente separado em ambiente_tipo + ambiente_tema
- Ambiguidade 3: status = ok / parcial / nao_classificado
- Ambiguidade 4: parser v1 so estrutura pastas de ano; tematicas viram v1.1
"""

from __future__ import annotations

import pytest

from catalogo.parser import ParsedPath, parse_path

SHARE_ROOT = "/mnt/photo-library/photos"

# Vocabulario de teste — replica os seeds mas isolado do banco.
# Termos ja normalizados (unidecode + lowercase).
VOCAB_TIPO: dict[str, str] = {
    "ensaios": "ensaio",
    "ensaio": "ensaio",
    "produtos": "produtos",
    "produto": "produtos",
    "quartinhos": "quartinhos",
    "quartinho": "quartinhos",
    "arquitetos": "arquitetos",
    "arquiteto": "arquitetos",
    "influenciadores": "influenciadores",
    "influenciador": "influenciadores",
}


def _parse(rel_path: str) -> ParsedPath:
    """Helper: monta o path completo e chama o parser."""
    return parse_path(f"{SHARE_ROOT}/{rel_path}", vocab_tipo=VOCAB_TIPO)


# ============================================================================
# 4 PATHS CANONICOS (spec §4.2)
# ============================================================================


def test_canonico_arquiteto_com_quarto_aninhado():
    """Arquiteto com quarto aninhado. Ambiente_tema preserva o aninhamento com ' > '."""
    p = _parse(
        "2026/COLEÇÃO 2026 - ARQUITETOS/ALICE MARTINS/QUARTO - LUCAS E LIA/LUCAS/"
        "quarto-infantil-masculino-grid-cinza....jpg"
    )
    assert p.ano == 2026
    assert p.tipo == "arquitetos"
    assert p.colecao == "colecao 2026"
    assert p.pessoa == "alice martins"
    assert p.pessoa_tipo == "arquiteto"
    assert p.ambiente_tipo == "quarto"
    assert p.ambiente_tema == "lucas e lia > lucas"
    assert p.categoria is None
    assert p.drop_numero is None
    assert p.drop_tema is None
    assert p.slug_arquivo == "quarto-infantil-masculino-grid-cinza"
    assert p.nome_arquivo == "quarto-infantil-masculino-grid-cinza....jpg"
    assert p.status == "ok"
    assert p.pendentes == []


def test_canonico_ensaio_pessoa_colecao_todo_dia():
    """Ensaio com pessoa+colecao no mesmo segmento e DROP tematico."""
    p = _parse(
        "2026/COLEÇÃO 2026 - ENSAIOS/PEDRO - COLEÇÃO TODO DIA/"
        "DROP 4 - PESCAR E ACAMPAR/"
        "Lançamento-coleção-todo-dia-marca (70).jpg"
    )
    assert p.ano == 2026
    assert p.tipo == "ensaio"
    # colecao do segmento pessoa+colecao SOBRESCREVE colecao do segmento tipo:
    assert p.colecao == "colecao todo dia"
    assert p.pessoa == "pedro"
    assert p.pessoa_tipo is None  # ensaio nao comprova se e influenciador, modelo ou parceiro
    assert p.drop_numero == 4
    assert p.drop_tema == "pescar e acampar"
    assert p.ambiente_tipo is None
    assert p.ambiente_tema is None
    assert p.categoria is None
    assert p.slug_arquivo == "lancamento-colecao-todo-dia-marca"
    assert p.status == "ok"


def test_canonico_produto_bonecas():
    """Produto: pasta filha e' categoria (ex.: BONECAS)."""
    p = _parse("2026/COLEÇÃO 2026 - PRODUTOS/BONECAS/boneca-de-pano-marca-fada-das-flores-1.jpg")
    assert p.ano == 2026
    assert p.tipo == "produtos"
    assert p.colecao == "colecao 2026"
    assert p.categoria == "bonecas"
    assert p.pessoa is None
    assert p.ambiente_tipo is None
    assert p.ambiente_tema is None
    assert p.drop_numero is None
    assert p.slug_arquivo == "boneca-de-pano-marca-fada-das-flores"
    assert p.status == "ok"


def test_canonico_quartinho_cachorros():
    """Quartinho: 'QUARTO INFANTIL X' vira ambiente_tipo='quarto infantil', ambiente_tema='X'."""
    p = _parse(
        "2026/COLEÇÃO 2026 - QUARTINHOS/QUARTO INFANTIL CACHORRINHOS/"
        "quarto-infantil-tema-cachorros-marca-2026-1.jpg"
    )
    assert p.ano == 2026
    assert p.tipo == "quartinhos"
    assert p.colecao == "colecao 2026"
    assert p.ambiente_tipo == "quarto infantil"
    assert p.ambiente_tema == "cachorrinhos"
    assert p.categoria is None
    assert p.pessoa is None
    assert p.slug_arquivo == "quarto-infantil-tema-cachorros-marca-2026"
    assert p.status == "ok"


def test_canonico_influenciador_marketplace_internacional():
    p = _parse(
        "2026/COLEÇÃO 2026 - INFLUENCIADORES/INTERNACIONAL/"
        "STUDIO.EXEMPLO/influencer-studio.exemplo (1).jpeg"
    )
    assert p.tipo == "influenciadores"
    assert p.pessoa == "studio.exemplo"
    assert p.pessoa_tipo == "influenciador"
    assert p.formato_foto == "marketplace internacional"
    assert p.status == "ok"


def test_canonico_influenciador_nacional_com_quarto():
    p = _parse("2026/COLEÇÃO 2026 - INFLUENCIADORES/NACIONAL/QUARTO - CLARA SOUZA (LUCAS)/foto.jpg")
    assert p.pessoa == "clara souza"
    assert p.pessoa_tipo == "influenciador"
    assert p.formato_foto is None
    assert p.ambiente_tipo == "quarto"
    assert p.ambiente_tema == "lucas"
    assert p.status == "ok"


def test_crop_e_variante_pesquisavel():
    p = _parse("2026/COLEÇÃO 2026 - ARQUITETOS/MARINA COSTA/QUARTO - TENIS/CROP/foto.jpg")
    assert p.variante == "crop"
    assert p.status == "ok"


# ============================================================================
# 2 CASOS DE DEGRADACAO (spec §4.2 obrigatorios)
# ============================================================================


def test_degradacao_arquivo_direto_na_raiz_do_ano():
    """Arquivo solto em 2015/foto.jpg — ano existe, mas nenhuma estrutura."""
    p = _parse("2015/foto-solta-sem-estrutura.jpg")
    assert p.ano == 2015
    assert p.tipo is None
    assert p.colecao is None
    assert p.categoria is None
    assert p.pessoa is None
    assert p.status == "nao_classificado"
    # path_raw ainda precisa conter o slug para busca textual/CLIP funcionarem:
    assert "foto-solta-sem-estrutura" in p.path_raw
    assert p.slug_arquivo == "foto-solta-sem-estrutura"


@pytest.mark.parametrize(("pasta", "ano"), [("2017 - ok", 2017), ("2018 - ok", 2018)])
def test_pasta_anual_com_sufixo_ok(pasta: str, ano: int):
    """Pastas anuais reais auditadas podem carregar o marcador administrativo '- ok'."""
    p = _parse(f"{pasta}/foto-solta.jpg")
    assert p.ano == ano
    assert p.status == "nao_classificado"


def test_degradacao_segmento_desconhecido_dentro_de_produtos():
    """PRODUTOS/BONECAS/ZZZ_ESQUISITO/foto.jpg — ano+tipo ok, segmento extra pende."""
    p = _parse("2026/COLEÇÃO 2026 - PRODUTOS/BONECAS/ZZZ_ESQUISITO/boneca.jpg")
    assert p.ano == 2026
    assert p.tipo == "produtos"
    assert p.categoria == "bonecas"
    assert p.status == "parcial"
    assert "zzz_esquisito" in p.pendentes


# ============================================================================
# 1 CASO TEMATICO (v1.1 fara estrutura; v1 nao)
# ============================================================================


def test_tematica_insta_fica_nao_classificado_no_v1():
    """Pasta tematica da raiz: parser v1 nao entende. Fica indexavel via FTS/CLIP."""
    p = _parse("SOCIAL/janeiro-2024/post-lancamento-marca.jpg")
    assert p.ano is None
    assert p.tipo is None
    assert p.status == "nao_classificado"
    # Path bruto normalizado deve preservar tudo para FTS/CLIP:
    assert "social" in p.path_raw
    assert "janeiro" in p.path_raw
    assert "post-lancamento-marca" in p.path_raw


# ============================================================================
# NORMALIZACAO (base do parser — quebrar cedo se estiver errado)
# ============================================================================


@pytest.mark.parametrize(
    "raw,esperado",
    [
        ("COLEÇÃO 2026 - ENSAIOS", "colecao 2026 - ensaios"),
        ("ALICE MARTINS", "alice martins"),
        ("Lucas e Lívia", "lucas e livia"),
        ("  espacos   colapsados  ", "espacos colapsados"),
        ("PEDRO", "pedro"),
    ],
)
def test_normalizacao_segmento(raw: str, esperado: str):
    from catalogo.parser import normalizar_segmento

    assert normalizar_segmento(raw) == esperado


@pytest.mark.parametrize(
    "nome_arquivo,slug_esperado",
    [
        ("boneca-de-pano-marca-fada-das-flores-1.jpg", "boneca-de-pano-marca-fada-das-flores"),
        (
            "quarto-infantil-tema-cachorros-marca-2026-1.jpg",
            "quarto-infantil-tema-cachorros-marca-2026",
        ),
        ("Lançamento-coleção-todo-dia-marca (70).jpg", "lancamento-colecao-todo-dia-marca"),
        ("foto-abc-3_2_.jpg", "foto-abc"),
        ("quarto-infantil-masculino-grid-cinza....jpg", "quarto-infantil-masculino-grid-cinza"),
    ],
)
def test_slug_arquivo(nome_arquivo: str, slug_esperado: str):
    from catalogo.parser import slug_do_arquivo

    assert slug_do_arquivo(nome_arquivo) == slug_esperado
