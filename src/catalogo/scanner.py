"""Varredura read-only do acervo e associacao de proxies REDUZIDAS."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from catalogo.parser import normalizar_segmento


@dataclass(frozen=True, slots=True)
class ScannedImage:
    path: Path
    reduzida_path: Path | None = None
    reduzida_orfa: bool = False


@dataclass(slots=True)
class ScanResult:
    imagens: list[ScannedImage] = field(default_factory=list)
    ignorados_nao_imagem: int = 0
    pastas_ignoradas: int = 0


def scan_tree(
    raiz: Path,
    *,
    extensoes: set[str],
    reduzidas_pasta_nome: str = "reduzidas",
    segmentos_ignorados: set[str] | None = None,
    recursivo: bool = True,
) -> ScanResult:
    """Lista imagens sem abrir ou modificar arquivos do acervo."""

    extensoes_norm = {ext.casefold() for ext in extensoes}
    nome_reduzidas = normalizar_segmento(reduzidas_pasta_nome)
    ignorados_norm = {normalizar_segmento(item) for item in (segmentos_ignorados or set())}
    aceitos: list[Path] = []
    ignorados = 0
    pastas_ignoradas = 0

    pendentes = [raiz]
    while pendentes:
        diretorio = pendentes.pop()
        with os.scandir(diretorio) as entradas:
            for entrada in entradas:
                if entrada.is_dir(follow_symlinks=False):
                    if not recursivo:
                        continue
                    if normalizar_segmento(entrada.name) in ignorados_norm:
                        pastas_ignoradas += 1
                    else:
                        pendentes.append(Path(entrada.path))
                elif entrada.is_file(follow_symlinks=False):
                    path = Path(entrada.path)
                    if path.suffix.casefold() not in extensoes_norm:
                        ignorados += 1
                    else:
                        aceitos.append(path)

    originais = [
        path for path in aceitos if normalizar_segmento(path.parent.name) != nome_reduzidas
    ]
    por_pasta_nome = {
        (str(path.parent).casefold(), path.name.casefold()): path for path in originais
    }
    proxies: dict[Path, Path] = {}
    orfas: list[Path] = []

    for path in aceitos:
        if normalizar_segmento(path.parent.name) != nome_reduzidas:
            continue
        chave_original = (str(path.parent.parent).casefold(), path.name.casefold())
        original = por_pasta_nome.get(chave_original)
        if original is None:
            orfas.append(path)
        else:
            proxies[original] = path

    imagens = [ScannedImage(path=path, reduzida_path=proxies.get(path)) for path in originais]
    imagens.extend(ScannedImage(path=path, reduzida_orfa=True) for path in orfas)
    imagens.sort(key=lambda item: str(item.path).casefold())
    return ScanResult(
        imagens=imagens,
        ignorados_nao_imagem=ignorados,
        pastas_ignoradas=pastas_ignoradas,
    )


def validar_mount_readonly(raiz: Path, *, mounts_text: str | None = None) -> None:
    """Aborta se a raiz nao estiver dentro de uma montagem CIFS somente leitura."""

    texto = mounts_text
    if texto is None:
        texto = Path("/proc/mounts").read_text(encoding="utf-8")

    raiz_resolvida = raiz.resolve()
    candidatos: list[tuple[Path, str, set[str]]] = []
    for linha in texto.splitlines():
        campos = linha.split()
        if len(campos) < 4:
            continue
        mount_path = Path(campos[1].replace("\\040", " ")).resolve()
        try:
            raiz_resolvida.relative_to(mount_path)
        except ValueError:
            continue
        candidatos.append((mount_path, campos[2], set(campos[3].split(","))))

    if not candidatos:
        raise RuntimeError(f"Nenhuma montagem CIFS encontrada para {raiz}")
    _, fs_type, opcoes = max(candidatos, key=lambda item: len(item[0].parts))
    if fs_type != "cifs":
        raise RuntimeError(f"A montagem CIFS esperada para {raiz} nao foi encontrada")
    if "ro" not in opcoes or "rw" in opcoes:
        raise RuntimeError(f"O acervo deve estar montado como somente leitura: {raiz}")
