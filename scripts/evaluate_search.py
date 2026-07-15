"""Avalia consultas PT-BR representativas contra o catálogo visual."""

from __future__ import annotations

import sys
from pathlib import Path

from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo.db import connect  # noqa: E402
from catalogo.search import ClipTextEmbedder, buscar_hibrida  # noqa: E402

CONSULTAS = [
    ("quartinho infantil tema cachorros", ("cachorr",)),
    ("boneca de pano fada das flores", ("boneca", "fada")),
    ("quarto infantil tema espaço", ("espaco",)),
    ("quarto infantil tema tênis", ("tenis",)),
    ("papel de parede listrado vermelho", ("listr", "vermelh")),
    ("quarto da influenciadora Clara Souza", ("clara", "souza")),
    ("capa de edredom infantil arco-íris de fadas", ("capa-de-edredom", "arco-iris")),
    ("crianças pescando e acampando", ("pescar", "acampar")),
    ("quarto infantil colorido", ("quarto", "infantil")),
    ("foto de influenciador para marketplace internacional", ("influencer",)),
]


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("catalogo.db")
    conn = connect(db_path)
    try:
        modelo = conn.execute("SELECT valor FROM config WHERE chave='modelo_embedding'").fetchone()[
            "valor"
        ]
    finally:
        conn.close()

    encoder = ClipTextEmbedder(modelo)
    acertos = 0
    for numero, (consulta, termos) in enumerate(CONSULTAS, 1):
        resultados = buscar_hibrida(db_path, consulta, embedder=encoder, limit=10)
        paths = [str(item["path"]) for item in resultados]
        paths_normalizados = [unidecode(path).lower() for path in paths]
        acertou = any(all(termo in path for termo in termos) for path in paths_normalizados)
        acertos += int(acertou)
        print(f"\n[{numero:02d}] {'PASS' if acertou else 'REVIEW'} — {consulta}")
        for posicao, item in enumerate(resultados[:5], 1):
            print(f"  {posicao}. {item['score_hibrido']:.4f}  {item['path']}")
    print(f"\nRESULTADO_HEURISTICO={acertos}/{len(CONSULTAS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
