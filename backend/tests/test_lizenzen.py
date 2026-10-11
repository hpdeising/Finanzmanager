# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lizenzen aller installierten Python-Abhängigkeiten gegen die Liste in CLAUDE.md prüfen.

Die erlaubten Lizenzfamilien werden aus CLAUDE.md gelesen, damit es nur eine Quelle
gibt. Unbekannte oder fehlende Lizenzangaben gelten als „unklare Lizenz“ und sind
damit verboten.
"""

import re
from importlib.metadata import Distribution, distributions
from pathlib import Path

import pytest

CLAUDE_MD = Path(__file__).resolve().parents[2] / "CLAUDE.md"

# SPDX-Kennung (PEP 639) → Lizenzfamilie, wie sie in CLAUDE.md genannt ist.
SPDX_FAMILIE: dict[str, str] = {
    "MIT": "MIT",
    "BSD-2-Clause": "BSD",
    "BSD-3-Clause": "BSD",
    "ISC": "ISC",
    "Apache-2.0": "Apache-2.0",
    "MPL-2.0": "MPL-2.0",
    "PSF-2.0": "PSF-2.0",
    "Python-2.0": "PSF-2.0",
    "LGPL-2.1-only": "LGPL",
    "LGPL-2.1-or-later": "LGPL",
    "LGPL-3.0-only": "LGPL",
    "LGPL-3.0-or-later": "LGPL",
    # „or-later“ erlaubt die Nutzung unter GPL-3.0; GPL-2.0-only bleibt verboten.
    "GPL-2.0-or-later": "GPL-3.0",
    "GPL-3.0-only": "GPL-3.0",
    "GPL-3.0-or-later": "GPL-3.0",
    "AGPL-3.0-only": "AGPL-3.0",
    "AGPL-3.0-or-later": "AGPL-3.0",
}

# Letztes Segment eines Trove-Klassifikators „License :: …“ → Lizenzfamilie.
KLASSIFIKATOR_FAMILIE: dict[str, str] = {
    "MIT License": "MIT",
    "BSD License": "BSD",
    "ISC License (ISCL)": "ISC",
    "Apache Software License": "Apache-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "GNU Lesser General Public License v2 (LGPLv2)": "LGPL",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL",
    "GNU Library or Lesser General Public License (LGPL)": "LGPL",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0",
    "GNU Affero General Public License v3": "AGPL-3.0",
    "GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0",
}


def erlaubte_familien(claude_md: str) -> frozenset[str]:
    """Liste „Erlaubte Lizenzen für Abhängigkeiten“ aus dem Text von CLAUDE.md."""
    treffer = re.search(r"Erlaubte Lizenzen für Abhängigkeiten: (.+?)\.\s", claude_md)
    if treffer is None:
        msg = "CLAUDE.md enthält keine Liste „Erlaubte Lizenzen für Abhängigkeiten“."
        raise ValueError(msg)
    return frozenset(name.strip() for name in treffer.group(1).split(","))


def erlaubt_nach_spdx(ausdruck: str, erlaubt: frozenset[str]) -> bool:
    """SPDX-Ausdruck prüfen.

    Reiner OR-Ausdruck: eine erlaubte Alternative genügt. Alles andere (AND,
    Klammern, WITH-Ausnahmen): jede genannte Kennung muss erlaubt sein.
    """
    kennungen = [k for k in re.findall(r"[A-Za-z0-9.+-]+", ausdruck) if k not in {"AND", "OR"}]
    if not kennungen:
        return False
    zulaessig = [SPDX_FAMILIE.get(k) in erlaubt for k in kennungen]
    nur_oder = " OR " in ausdruck and " AND " not in ausdruck and "(" not in ausdruck
    return any(zulaessig) if nur_oder else all(zulaessig)


def erlaubt_nach_klassifikatoren(klassen: list[str], erlaubt: frozenset[str]) -> bool:
    """Mehrere Lizenz-Klassifikatoren bedeuten Wahlfreiheit; einer muss erlaubt sein."""
    return any(KLASSIFIKATOR_FAMILIE.get(k) in erlaubt for k in klassen)


def lizenzangabe(dist: Distribution, erlaubt: frozenset[str]) -> tuple[str, bool]:
    """Lizenzangabe eines Pakets und ob sie erlaubt ist.

    Reihenfolge: ``License-Expression`` (PEP 639), dann Klassifikatoren, dann das
    Freitextfeld ``License``.
    """
    metadaten = dist.metadata
    ausdruck = metadaten.get("License-Expression")
    if ausdruck:
        return ausdruck, erlaubt_nach_spdx(ausdruck, erlaubt)
    klassen = [
        str(k).split(" :: ")[-1]
        for k in metadaten.get_all("Classifier", [])
        if str(k).startswith("License ::")
    ]
    if klassen:
        return "; ".join(klassen), erlaubt_nach_klassifikatoren(klassen, erlaubt)
    freitext = (metadaten.get("License") or "").strip()
    if not freitext:
        return "keine Angabe", False
    return freitext.splitlines()[0], erlaubt_nach_spdx(freitext, erlaubt)


@pytest.fixture(scope="module")
def erlaubt() -> frozenset[str]:
    return erlaubte_familien(CLAUDE_MD.read_text(encoding="utf-8"))


# --- Selbsttests ---------------------------------------------------------------

BEISPIEL_ERLAUBT = frozenset({"MIT", "BSD", "Apache-2.0", "PSF-2.0", "LGPL", "GPL-3.0"})


def test_liste_wird_aus_claude_md_gelesen() -> None:
    text = "- Erlaubte Lizenzen für Abhängigkeiten: MIT, BSD, PSF-2.0. KERN-UX nur unverändert.\n"
    assert erlaubte_familien(text) == {"MIT", "BSD", "PSF-2.0"}


def test_fehlende_liste_ist_ein_fehler() -> None:
    with pytest.raises(ValueError, match="Erlaubte Lizenzen"):
        erlaubte_familien("keine Liste")


@pytest.mark.parametrize(
    ("ausdruck", "erwartet"),
    [
        ("MIT", True),
        ("PSF-2.0", True),
        ("Apache-2.0 OR BSD-2-Clause", True),
        ("BUSL-1.1 OR MIT", True),
        ("MIT AND BUSL-1.1", False),
        ("GPL-2.0-only", False),
        ("GPL-2.0-or-later", True),
        ("SSPL-1.0", False),
        ("GPL-3.0-or-later WITH Classpath-exception-2.0", False),
        ("", False),
    ],
)
def test_spdx_pruefung(ausdruck: str, erwartet: bool) -> None:
    assert erlaubt_nach_spdx(ausdruck, BEISPIEL_ERLAUBT) is erwartet


@pytest.mark.parametrize(
    ("klassen", "erwartet"),
    [
        (["MIT License"], True),
        (["Python Software Foundation License"], True),
        (["Other/Proprietary License"], False),
        (["OSI Approved"], False),
        (["Other/Proprietary License", "BSD License"], True),
    ],
)
def test_klassifikator_pruefung(klassen: list[str], erwartet: bool) -> None:
    assert erlaubt_nach_klassifikatoren(klassen, BEISPIEL_ERLAUBT) is erwartet


def test_abbildungen_zeigen_nur_auf_familien_aus_claude_md(erlaubt: frozenset[str]) -> None:
    familien = set(SPDX_FAMILIE.values()) | set(KLASSIFIKATOR_FAMILIE.values())
    assert familien <= erlaubt, f"Nicht in CLAUDE.md erlaubt: {sorted(familien - erlaubt)}"


# --- Prüfung der installierten Abhängigkeiten --------------------------------------


def test_lizenzen_der_abhaengigkeiten(erlaubt: frozenset[str]) -> None:
    verstoesse: dict[str, str] = {}
    for dist in distributions():
        angabe, ist_erlaubt = lizenzangabe(dist, erlaubt)
        if not ist_erlaubt:
            verstoesse[dist.metadata["Name"]] = angabe
    assert verstoesse == {}, (
        f"Lizenzen nicht auf der Liste in CLAUDE.md: {verstoesse}. "
        "Entweder Abhängigkeit ersetzen oder die Liste in CLAUDE.md bewusst ändern."
    )
