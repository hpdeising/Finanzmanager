# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maschinelle Prüfung von Regeln aus CLAUDE.md.

Die Prüffunktionen werden zuerst an Beispielen getestet. Ohne diese Selbsttests
könnte eine defekte Prüfung unbemerkt immer grün melden.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"
TESTS = BACKEND / "tests"
KERN_GELD = APP / "kern" / "geld"

SPDX_KOPFZEILE = "# SPDX-License-Identifier: AGPL-3.0-or-later"
VERBOTENE_PYTEST_AUFRUFE = frozenset({"skip", "skipif", "xfail", "importorskip"})


def python_dateien(wurzel: Path) -> list[Path]:
    """Alle Python-Dateien unterhalb von ``wurzel``, sortiert."""
    return sorted(wurzel.rglob("*.py"))


def float_fundstellen(quelltext: str) -> list[int]:
    """Zeilen mit Fließkomma-Literalen oder dem Namen ``float``.

    CLAUDE.md: Beträge ausschließlich als ``decimal.Decimal``; ``float`` ist in
    ``backend/app/`` verboten.
    """
    return sorted(
        knoten.lineno
        for knoten in ast.walk(ast.parse(quelltext))
        if (isinstance(knoten, ast.Constant) and isinstance(knoten.value, float))
        or (isinstance(knoten, ast.Name) and knoten.id == "float")
    )


def quantize_fundstellen(quelltext: str) -> list[int]:
    """Zeilen mit Aufrufen von ``quantize``.

    CLAUDE.md: Gerundet wird nur über die zentrale Funktion in ``kern/geld``.
    """
    return sorted(
        knoten.lineno
        for knoten in ast.walk(ast.parse(quelltext))
        if isinstance(knoten, ast.Attribute) and knoten.attr == "quantize"
    )


def skip_xfail_fundstellen(quelltext: str) -> list[int]:
    """Zeilen, die Tests überspringen oder als ``xfail`` markieren.

    Erfasst ``pytest.skip``, ``pytest.mark.skipif``, ``pytest.xfail`` und
    ``pytest.importorskip``. CLAUDE.md: Tests nicht überspringen, nicht als
    ``xfail`` markieren.
    """
    zeilen: list[int] = []
    for knoten in ast.walk(ast.parse(quelltext)):
        if not isinstance(knoten, ast.Attribute) or knoten.attr not in VERBOTENE_PYTEST_AUFRUFE:
            continue
        basis = knoten.value
        if isinstance(basis, ast.Attribute) and basis.attr == "mark":
            basis = basis.value
        if isinstance(basis, ast.Name) and basis.id == "pytest":
            zeilen.append(knoten.lineno)
    return sorted(zeilen)


def hat_spdx_kopfzeile(quelltext: str) -> bool:
    """Ob die erste Zeile die SPDX-Kopfzeile der Projektlizenz ist."""
    return quelltext.splitlines()[:1] == [SPDX_KOPFZEILE]


def lies(datei: Path) -> str:
    return datei.read_text(encoding="utf-8")


def relativ(datei: Path) -> str:
    return datei.relative_to(BACKEND).as_posix()


# --- Selbsttests der Prüffunktionen --------------------------------------------


@pytest.mark.parametrize(
    ("quelltext", "erwartet"),
    [
        ("betrag = 1.5\n", [1]),
        ("x = 1\ny = float(x)\n", [2]),
        ("def f(a: float) -> None: ...\n", [1]),
        ("from decimal import Decimal\nbetrag = Decimal('1.5')\n", []),
        ("anzahl = 3\n", []),
    ],
)
def test_float_pruefung_erkennt_fliesskomma(quelltext: str, erwartet: list[int]) -> None:
    assert float_fundstellen(quelltext) == erwartet


@pytest.mark.parametrize(
    ("quelltext", "erwartet"),
    [
        ("x = betrag.quantize(cent)\n", [1]),
        ("x = runde(betrag)\n", []),
    ],
)
def test_quantize_pruefung(quelltext: str, erwartet: list[int]) -> None:
    assert quantize_fundstellen(quelltext) == erwartet


@pytest.mark.parametrize(
    ("quelltext", "erwartet"),
    [
        ("import pytest\n@pytest.mark.skip\ndef test_a() -> None: ...\n", [2]),
        ("import pytest\n@pytest.mark.xfail\ndef test_a() -> None: ...\n", [2]),
        ("import pytest\npytest.skip('grund')\n", [2]),
        ("import pytest\npytest.importorskip('modul')\n", [2]),
        (
            "import pytest\n@pytest.mark.parametrize('a', [1])\ndef test_a(a: int) -> None: ...\n",
            [],
        ),
    ],
)
def test_skip_xfail_pruefung(quelltext: str, erwartet: list[int]) -> None:
    assert skip_xfail_fundstellen(quelltext) == erwartet


def test_spdx_pruefung() -> None:
    assert hat_spdx_kopfzeile(f"{SPDX_KOPFZEILE}\n'''Doc.'''\n")
    assert not hat_spdx_kopfzeile("'''Doc.'''\n")
    assert not hat_spdx_kopfzeile("")


# --- Prüfung des Repositorys --------------------------------------------------


def test_kein_float_in_app() -> None:
    funde = {
        relativ(datei): zeilen
        for datei in python_dateien(APP)
        if (zeilen := float_fundstellen(lies(datei)))
    }
    assert funde == {}, f"float in backend/app/ ist verboten (CLAUDE.md, Geld): {funde}"


def test_quantize_nur_in_kern_geld() -> None:
    funde = {
        relativ(datei): zeilen
        for datei in python_dateien(APP)
        if not datei.is_relative_to(KERN_GELD) and (zeilen := quantize_fundstellen(lies(datei)))
    }
    assert funde == {}, f"Rundung nur über kern/geld (CLAUDE.md, Geld): {funde}"


def test_keine_uebersprungenen_tests() -> None:
    funde = {
        relativ(datei): zeilen
        for datei in python_dateien(TESTS)
        if (zeilen := skip_xfail_fundstellen(lies(datei)))
    }
    assert funde == {}, f"Tests nicht überspringen oder als xfail markieren (CLAUDE.md): {funde}"


def test_spdx_kopfzeile_in_allen_python_dateien() -> None:
    ohne = [
        relativ(datei)
        for datei in python_dateien(APP) + python_dateien(TESTS)
        if not hat_spdx_kopfzeile(lies(datei))
    ]
    assert ohne == [], f"Erste Zeile muss '{SPDX_KOPFZEILE}' sein: {ohne}"
