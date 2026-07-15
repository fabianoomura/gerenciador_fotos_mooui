"""Testes da varredura read-only e da associacao de REDUZIDAS."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalogo.scanner import scan_tree, validar_mount_readonly


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_scan_filtra_extensoes_e_contabiliza_ignorados(tmp_path: Path) -> None:
    _touch(tmp_path / "foto.JPG")
    _touch(tmp_path / "imagem.webp")
    _touch(tmp_path / "arte.psd")
    _touch(tmp_path / "atalho.lnk")

    resultado = scan_tree(tmp_path, extensoes={".jpg", ".webp"})

    assert {item.path.name for item in resultado.imagens} == {"foto.JPG", "imagem.webp"}
    assert resultado.ignorados_nao_imagem == 2


def test_reduzida_vira_proxy_e_nao_registro(tmp_path: Path) -> None:
    original = tmp_path / "colecao" / "foto-01.jpg"
    reduzida = tmp_path / "colecao" / "REDUZIDAS" / "foto-01.jpg"
    _touch(original)
    _touch(reduzida)

    resultado = scan_tree(tmp_path, extensoes={".jpg"})

    assert len(resultado.imagens) == 1
    assert resultado.imagens[0].path == original
    assert resultado.imagens[0].reduzida_path == reduzida


def test_reduzida_orfa_vira_registro_sinalizado(tmp_path: Path) -> None:
    orfa = tmp_path / "colecao" / "reduzidas" / "sem-original.jpg"
    _touch(orfa)

    resultado = scan_tree(tmp_path, extensoes={".jpg"})

    assert len(resultado.imagens) == 1
    assert resultado.imagens[0].path == orfa
    assert resultado.imagens[0].reduzida_orfa is True


def test_validar_mount_readonly_aceita_ro_e_rejeita_rw(tmp_path: Path) -> None:
    mount = str(tmp_path).replace(" ", "\\040")
    validar_mount_readonly(tmp_path, mounts_text=f"//server/share {mount} cifs ro,vers=3.0 0 0")

    with pytest.raises(RuntimeError, match="somente leitura"):
        validar_mount_readonly(
            tmp_path,
            mounts_text=f"//server/share {mount} cifs rw,vers=3.0 0 0",
        )


def test_validar_mount_readonly_rejeita_path_sem_mount(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="montagem CIFS"):
        validar_mount_readonly(tmp_path, mounts_text="tmpfs /tmp tmpfs rw 0 0")


def test_scan_ignora_pasta_administrativa_configurada(tmp_path: Path) -> None:
    _touch(tmp_path / "produto" / "foto.jpg")
    _touch(tmp_path / "0 - ARQUIVOS ZIP" / "duplicada.jpg")

    resultado = scan_tree(
        tmp_path,
        extensoes={".jpg"},
        segmentos_ignorados={"0 - arquivos zip"},
    )

    assert [item.path.name for item in resultado.imagens] == ["foto.jpg"]
    assert resultado.pastas_ignoradas == 1


def test_scan_nao_recursivo_pega_apenas_arquivos_da_raiz(tmp_path: Path) -> None:
    _touch(tmp_path / "solta.jpg")
    _touch(tmp_path / "pasta" / "interna.jpg")

    resultado = scan_tree(tmp_path, extensoes={".jpg"}, recursivo=False)

    assert [item.path.name for item in resultado.imagens] == ["solta.jpg"]
