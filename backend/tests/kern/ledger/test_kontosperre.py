# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buchungsdatum, Kontosperre und Stornoschutz über die Python-API (E-26 bis E-28).

Die API prüft vorab und meldet verständliche Fehler; die Datenbank erzwingt dieselben
Regeln (test_kontosperre_sql.py). Welches Buchungsdatum eine Buchung bekommt, entscheidet
ein Modul; ohne Angabe gilt der offene Zeitraum: Buchungsdatum gleich Wertstellung.
"""

import uuid
from collections.abc import Collection
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.kern.ledger import (
    Buchung,
    BuchungUngueltigError,
    KontoGesperrtError,
    KontoSperre,
    KontoUnbekanntError,
    PostingEingabe,
    SperreUngueltigError,
    StornoNichtMoeglichError,
    buche,
    buchen,
    halte_konten,
    saldo,
    sperrdatum,
    sperre,
    sperre_konten,
    storniere,
)
from tests.datenbank import constraint_name, pruefe_aufgeschobene
from tests.kern.ledger.conftest import Konten

DAVOR = date(2024, 3, 1)
STICHTAG = date(2024, 6, 30)
DANACH = date(2024, 8, 1)


def zahlung(
    session: Session,
    konten: Konten,
    *,
    wertstellung: date = DAVOR,
    buchungsdatum: date | None = None,
    stornierbar: bool = True,
    betrag: str = "10",
) -> Buchung:
    return buche(
        session,
        haushalt_id=konten.haushalt_id,
        art="test.zahlung",
        wertstellung=wertstellung,
        buchungsdatum=buchungsdatum,
        stornierbar=stornierbar,
        postings=[
            PostingEingabe(konten.hauptforderung, Decimal(betrag)),
            PostingEingabe(konten.eroeffnung, -Decimal(betrag)),
        ],
    )


# --- Buchungsdatum ------------------------------------------------------------------------


def test_ohne_angabe_ist_das_buchungsdatum_die_wertstellung(
    session: Session, konten: Konten
) -> None:
    buchung = zahlung(session, konten)
    session.refresh(buchung)
    assert (buchung.wertstellung, buchung.buchungsdatum, buchung.stornierbar) == (
        DAVOR,
        DAVOR,
        True,
    )


def test_spaeteres_buchungsdatum(session: Session, konten: Konten) -> None:
    buchung = zahlung(session, konten, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)
    session.refresh(buchung)
    assert buchung.buchungsdatum == DANACH


def test_buchungsdatum_nicht_vor_der_wertstellung(session: Session, konten: Konten) -> None:
    with pytest.raises(BuchungUngueltigError, match="Buchungsdatum"):
        zahlung(session, konten, wertstellung=DANACH, buchungsdatum=DAVOR)


def test_buchungsdatum_ist_ein_datum(session: Session, konten: Konten) -> None:
    with pytest.raises(TypeError, match="Buchungsdatum"):
        zahlung(session, konten, buchungsdatum=datetime(2024, 8, 1, 12, 0))  # noqa: DTZ001


def test_saldo_zaehlt_nach_buchungsdatum(session: Session, konten: Konten) -> None:
    """Kap. 4.1: Saldo nach Buchungsdatum; Zinsen und Anrechnung rechnet das Modul."""
    zahlung(session, konten, wertstellung=DAVOR, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=STICHTAG) == 0
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=DANACH) == Decimal(10)


# --- Kontosperre --------------------------------------------------------------------------


def test_ohne_sperre_kein_sperrdatum(session: Session, konten: Konten) -> None:
    assert sperrdatum(session, konto_id=konten.hauptforderung) is None


def test_sperre_setzen_und_lesen(session: Session, konten: Konten) -> None:
    sperre_konten(session, konto_ids=[konten.hauptforderung, konten.eroeffnung], bis=STICHTAG)
    assert sperrdatum(session, konto_id=konten.hauptforderung) == STICHTAG
    assert sperrdatum(session, konto_id=konten.eroeffnung) == STICHTAG
    assert sperrdatum(session, konto_id=konten.zinsaufwand) is None


@pytest.mark.parametrize("bis", [STICHTAG, DAVOR], ids=["gleich", "frueher"])
def test_sperrdatum_steigt_nur(session: Session, konten: Konten, bis: date) -> None:
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    with pytest.raises(SperreUngueltigError, match="steigt"):
        sperre_konten(session, konto_ids=[konten.hauptforderung], bis=bis)


def test_sperre_unbekanntes_konto(session: Session) -> None:
    with pytest.raises(KontoUnbekanntError):
        sperre_konten(session, konto_ids=[uuid.uuid4()], bis=STICHTAG)
    with pytest.raises(KontoUnbekanntError):
        halte_konten(session, konto_ids=[uuid.uuid4()])
    with pytest.raises(KontoUnbekanntError):
        sperrdatum(session, konto_id=uuid.uuid4())


def test_sperre_bis_ist_ein_datum(session: Session, konten: Konten) -> None:
    with pytest.raises(TypeError, match="Sperrdatum"):
        sperre_konten(
            session,
            konto_ids=[konten.hauptforderung],
            bis=datetime(2024, 6, 30, 12, 0),  # noqa: DTZ001
        )


@pytest.mark.parametrize("buchungsdatum", [DAVOR, STICHTAG], ids=["davor", "am_sperrdatum"])
def test_buchung_in_gesperrten_zeitraum(
    session: Session, konten: Konten, buchungsdatum: date
) -> None:
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    with pytest.raises(KontoGesperrtError, match="gesperrt"):
        zahlung(session, konten, wertstellung=DAVOR, buchungsdatum=buchungsdatum)


def test_nachtraegliche_buchung_mit_tag_der_erfassung(session: Session, konten: Konten) -> None:
    """E-26: Wertstellung im festgeschriebenen Zeitraum, Buchungsdatum danach."""
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    zahlung(session, konten, wertstellung=DAVOR, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=STICHTAG) == 0


def test_halte_konten_in_eigener_transaktion(session: Session, konten: Konten) -> None:
    """Wer die Konten hält, darf selbst weiter buchen und sperren."""
    halte_konten(session, konto_ids=[konten.hauptforderung, konten.eroeffnung])
    zahlung(session, konten)
    sperre_konten(session, konto_ids=[konten.hauptforderung, konten.eroeffnung], bis=STICHTAG)
    pruefe_aufgeschobene(session)
    assert sperrdatum(session, konto_id=konten.hauptforderung) == STICHTAG


# --- Storno --------------------------------------------------------------------------------


def test_storno_uebernimmt_das_buchungsdatum_des_originals(
    session: Session, konten: Konten
) -> None:
    original = zahlung(session, konten, buchungsdatum=DANACH)
    storno = storniere(session, buchung_id=original.id)
    pruefe_aufgeschobene(session)
    session.refresh(storno)
    assert (storno.wertstellung, storno.buchungsdatum) == (DAVOR, DANACH)


def test_storno_mit_spaeterem_buchungsdatum(session: Session, konten: Konten) -> None:
    original = zahlung(session, konten)
    storno = storniere(session, buchung_id=original.id, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)
    session.refresh(storno)
    assert (storno.wertstellung, storno.buchungsdatum) == (DAVOR, DANACH)


def test_storno_nicht_vor_dem_buchungsdatum_des_originals(session: Session, konten: Konten) -> None:
    original = zahlung(session, konten, buchungsdatum=DANACH)
    with pytest.raises(StornoNichtMoeglichError, match="Buchungsdatum"):
        storniere(session, buchung_id=original.id, buchungsdatum=STICHTAG)


def test_storno_buchungsdatum_ist_ein_datum(session: Session, konten: Konten) -> None:
    original = zahlung(session, konten)
    with pytest.raises(TypeError, match="Buchungsdatum"):
        storniere(
            session,
            buchung_id=original.id,
            buchungsdatum=datetime(2024, 8, 1, 12, 0),  # noqa: DTZ001
        )


def test_nicht_stornierbare_buchung(session: Session, konten: Konten) -> None:
    """E-28: z. B. die Buchungen einer Festschreibung; der Kern kennt nur das Merkmal."""
    original = zahlung(session, konten, stornierbar=False)
    with pytest.raises(StornoNichtMoeglichError, match="nicht stornierbar"):
        storniere(session, buchung_id=original.id)


def test_stornierbar_ist_ein_wahrheitswert(session: Session, konten: Konten) -> None:
    with pytest.raises(TypeError, match="stornierbar"):
        zahlung(session, konten, stornierbar="nein")  # pyright: ignore[reportArgumentType]


def test_storno_in_gesperrten_zeitraum_braucht_spaeteres_buchungsdatum(
    session: Session, konten: Konten
) -> None:
    """E-26: Storno einer Buchung aus dem festgeschriebenen Zeitraum mit Tag der Erfassung."""
    original = zahlung(session, konten)
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    with pytest.raises(KontoGesperrtError):
        storniere(session, buchung_id=original.id)
    storno = storniere(session, buchung_id=original.id, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)
    session.refresh(storno)
    assert storno.wertstellung == DAVOR
    # Die Bücher des gesperrten Zeitraums bleiben, wie sie waren (Kap. 4.1).
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=STICHTAG) == Decimal(10)
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=DANACH) == 0


# --- Übersetzung der Datenbankfehler ---------------------------------------------------------


def keine_sperrdaten(session: Session, konto_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, date]:
    """Ersetzt die Vorabprüfung: Sie sieht eine Sperre noch nicht (Wettlauf)."""
    return {}


def test_sperre_im_wettlauf_wird_zu_konto_gesperrt(
    session: Session, konten: Konten, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sieht die Vorabprüfung eine Sperre noch nicht, lehnt die Datenbank ab (E-27)."""
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    monkeypatch.setattr(buchen, "sperrdaten", keine_sperrdaten)
    with pytest.raises(KontoGesperrtError) as fehler:
        zahlung(session, konten, wertstellung=DAVOR)
    assert constraint_name(fehler.value.__cause__ or fehler.value) == "posting_konto_gesperrt"
    assert str(konten.hauptforderung) not in str(fehler.value)


def test_fallendes_sperrdatum_im_wettlauf(
    session: Session, konten: Konten, monkeypatch: pytest.MonkeyPatch
) -> None:
    sperre_konten(session, konto_ids=[konten.hauptforderung], bis=STICHTAG)
    monkeypatch.setattr(sperre, "sperrdaten", keine_sperrdaten)
    with pytest.raises(SperreUngueltigError) as fehler:
        sperre_konten(session, konto_ids=[konten.hauptforderung], bis=DAVOR)
    assert constraint_name(fehler.value.__cause__ or fehler.value) == "konto_sperre_steigt"


def test_erfasst_am_der_sperre_setzt_die_datenbank() -> None:
    with pytest.raises(SperreUngueltigError, match="erfasst_am"):
        KontoSperre(konto_id=uuid.uuid4(), gesperrt_bis=STICHTAG, erfasst_am=datetime.now(UTC))
