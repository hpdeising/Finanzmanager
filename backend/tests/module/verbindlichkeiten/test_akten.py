# SPDX-License-Identifier: AGPL-3.0-or-later
"""Akten speichern und laden (Fachkonzept Kap. 4.2, 4.3, 4.5) gegen PostgreSQL.

Gespeichert wird mit Konten und Buchungen; geladen wird als Eingaben der Berechnung, wie sie
Zinsen, Anrechnung, Fristen, Verjährung und Status brauchen. Alle Namen sind erfunden.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kern.haushalt import lege_haushalt_an
from app.kern.ledger import Buchung, Konto, Posting, StornoNichtMoeglichError, saldo
from app.kern.stammdaten import lade_basiszinsreihe
from app.kern.zeit import ZEITZONE
from app.module.verbindlichkeiten.akten import (
    AkteUnbekanntError,
    EreignisUnbekanntError,
    GlaeubigerUnbekanntError,
    akten,
    erfasse_ereignis,
    erfasse_zahlung,
    lade_akte,
    lege_akte_an,
    lege_bestandteil_an,
    lege_glaeubiger_an,
    loesche_ereignis,
    storniere_zahlung,
)
from app.module.verbindlichkeiten.berechnung import berechne
from app.module.verbindlichkeiten.db import Akte, AkteKonto, EreignisZeile
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    Bestandteilart,
    EingabeUngueltigError,
    Ereignis,
    Ereignistyp,
    Gruppe,
    Tageszaehlung,
    Zahlung,
    Zinsregel,
    Zinsregeltyp,
)

T = date
D = Decimal
E = Ereignistyp
ENTSTANDEN = T(2024, 1, 15)
HF = Bestandteil(
    "hauptforderung",
    Bestandteilart.HAUPTFORDERUNG,
    D("1000.00"),
    [Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=T(2024, 2, 1))],
    ENTSTANDEN,
    faellig_am=T(2024, 1, 31),
)


def haushalt(session: Session) -> uuid.UUID:
    return lege_haushalt_an(session, betriebsart="einzel", bundesland="SH").id


def neue_akte(session: Session, **optionen: object) -> tuple[uuid.UUID, uuid.UUID]:
    haushalt_id = haushalt(session)
    glaeubiger_id = lege_glaeubiger_an(session, haushalt_id=haushalt_id, name="Muster Inkasso")
    akte_id = lege_akte_an(
        session,
        haushalt_id=haushalt_id,
        glaeubiger_id=glaeubiger_id,
        **optionen,  # pyright: ignore[reportArgumentType]
    )
    return haushalt_id, akte_id


def konten_mit_rolle(session: Session, haushalt_id: uuid.UUID, rolle: str) -> list[Konto]:
    return list(
        session.scalars(select(Konto).where(Konto.haushalt_id == haushalt_id, Konto.rolle == rolle))
    )


# --- Anlegen ----------------------------------------------------------------------------------


def test_akte_mit_zahlungskonto_und_konten_des_haushalts(session: Session) -> None:
    """Kap. 4.2: je Akte ein Zahlungskonto; je Haushalt Eröffnung, Zinsaufwand, Kostenaufwand
    und Externe Mittel."""
    haushalt_id, akte_id = neue_akte(session)
    (zahlungen,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.zahlungen")
    assert zahlungen.kontoart == "passiv"
    verknuepft = session.scalars(select(AkteKonto.konto_id).where(AkteKonto.akte_id == akte_id))
    assert set(verknuepft) == {zahlungen.id}
    for rolle, kontoart in [
        ("verbindlichkeiten.eroeffnung", "eigenkapital"),
        ("verbindlichkeiten.zinsaufwand", "aufwand"),
        ("verbindlichkeiten.kostenaufwand", "aufwand"),
        ("kern.externe_mittel", "eigenkapital"),
    ]:
        (konto,) = konten_mit_rolle(session, haushalt_id, rolle)
        assert konto.kontoart == kontoart


def test_konten_des_haushalts_nur_einmal(session: Session) -> None:
    haushalt_id, _ = neue_akte(session)
    glaeubiger_id = lege_glaeubiger_an(session, haushalt_id=haushalt_id, name="Beispiel AG")
    lege_akte_an(session, haushalt_id=haushalt_id, glaeubiger_id=glaeubiger_id)
    assert len(konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.eroeffnung")) == 1
    assert len(konten_mit_rolle(session, haushalt_id, "kern.externe_mittel")) == 1
    assert len(konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.zahlungen")) == 2


def test_glaeubiger_eines_anderen_haushalts(session: Session) -> None:
    fremd = lege_glaeubiger_an(session, haushalt_id=haushalt(session), name="Fremd GmbH")
    with pytest.raises(GlaeubigerUnbekanntError):
        lege_akte_an(session, haushalt_id=haushalt(session), glaeubiger_id=fremd)


def test_bestandteil_mit_konto_und_entstehungsbuchung(session: Session) -> None:
    """Kap. 4.3: Erfassung einer Altlast, Soll Eröffnung Altlasten, Haben Hauptforderung."""
    haushalt_id, akte_id = neue_akte(session)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=HF)
    (hf_konto,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.hauptforderung")
    (eroeffnung,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.eroeffnung")
    assert saldo(session, konto_id=hf_konto.id, stichtag=ENTSTANDEN) == D("-1000.00")
    assert saldo(session, konto_id=eroeffnung.id, stichtag=ENTSTANDEN) == D("1000.00")
    (buchung,) = session.scalars(
        select(Buchung).join(Posting).where(Posting.konto_id == hf_konto.id)
    )
    assert (buchung.art, buchung.wertstellung) == ("verbindlichkeiten.entstehung", ENTSTANDEN)
    verknuepft = set(
        session.scalars(select(AkteKonto.konto_id).where(AkteKonto.akte_id == akte_id))
    )
    assert hf_konto.id in verknuepft


def test_zinskonto_je_verzinslicher_zinsregel(session: Session) -> None:
    """Kap. 4.2: Zinsen, eines je Zinsregel; eine Pause ohne Verzinsung hat keins."""
    haushalt_id, akte_id = neue_akte(session)
    bestandteil = Bestandteil(
        "hauptforderung",
        Bestandteilart.HAUPTFORDERUNG,
        D("500.00"),
        [
            Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=T(2024, 2, 1), bis=T(2024, 12, 31)),
            Zinsregel(Zinsregeltyp.KEINE, ab=T(2025, 1, 1)),
            Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 6, 1), satz=D("4.5")),
        ],
        ENTSTANDEN,
    )
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=bestandteil)
    assert len(konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.zinsen")) == 2


def eroeffnungstag(session: Session, akte_id: uuid.UUID) -> date:
    """Kalendertag, an dem die Akte angelegt wurde, in der Zeitzone der Installation."""
    return session.get_one(Akte, akte_id).angelegt_am.astimezone(ZEITZONE).date()


def gegenbuchung(session: Session, haushalt_id: uuid.UUID, rolle: str) -> Buchung:
    (konto,) = konten_mit_rolle(session, haushalt_id, rolle)
    (buchung,) = session.scalars(select(Buchung).join(Posting).where(Posting.konto_id == konto.id))
    return buchung


@pytest.mark.parametrize(
    "art",
    [
        Bestandteilart.KOSTEN_VORGERICHTLICH,
        Bestandteilart.KOSTEN_VERFAHREN,
        Bestandteilart.KOSTEN_VOLLSTRECKUNG,
    ],
)
def test_kosten_nach_eroeffnung_gegen_kostenaufwand(session: Session, art: Bestandteilart) -> None:
    """Entscheidung vom 21.11.2026 (Kap. 4.3): Kosten, die nach Eröffnung der Akte entstehen,
    sind neue Kosten: Soll Kostenaufwand, Art verbindlichkeiten.kosten."""
    haushalt_id, akte_id = neue_akte(session)
    tag = eroeffnungstag(session, akte_id) + timedelta(days=1)
    kosten = Bestandteil("kosten", art, D("38.50"), (), tag)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=kosten)
    (aufwand,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.kostenaufwand")
    assert saldo(session, konto_id=aufwand.id, stichtag=tag) == D("38.50")
    buchung = gegenbuchung(session, haushalt_id, f"verbindlichkeiten.{art.value}")
    assert (buchung.art, buchung.wertstellung) == ("verbindlichkeiten.kosten", tag)


@pytest.mark.parametrize("abstand", [0, -1, -400])
def test_kosten_bis_zur_eroeffnung_gegen_eroeffnung(session: Session, abstand: int) -> None:
    """Kosten vom Tag der Eröffnung oder davor gehören zur Altlast: Soll Eröffnung Altlasten."""
    haushalt_id, akte_id = neue_akte(session)
    tag = eroeffnungstag(session, akte_id) + timedelta(days=abstand)
    kosten = Bestandteil("gv_kosten", Bestandteilart.KOSTEN_VOLLSTRECKUNG, D("38.50"), (), tag)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=kosten)
    (eroeffnung,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.eroeffnung")
    assert saldo(session, konto_id=eroeffnung.id, stichtag=tag) == D("38.50")
    buchung = gegenbuchung(session, haushalt_id, "verbindlichkeiten.kosten_vollstreckung")
    assert buchung.art == "verbindlichkeiten.entstehung"


def test_ohne_entstehungstag_gegen_eroeffnung_am_eroeffnungstag(session: Session) -> None:
    """Ohne entstanden_am: Eröffnung Altlasten, gebucht am Tag der Eröffnung der Akte."""
    haushalt_id, akte_id = neue_akte(session)
    ohne = Bestandteil("gv_kosten", Bestandteilart.KOSTEN_VOLLSTRECKUNG, D("10.00"))
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=ohne)
    buchung = gegenbuchung(session, haushalt_id, "verbindlichkeiten.kosten_vollstreckung")
    assert (buchung.art, buchung.wertstellung) == (
        "verbindlichkeiten.entstehung",
        eroeffnungstag(session, akte_id),
    )
    inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
    assert inhalt.bestandteile == (ohne,)


def test_hauptforderung_nach_eroeffnung_bleibt_altlast(session: Session) -> None:
    """Die Entscheidung betrifft Kosten; Hauptforderung und Zinsen bucht die Erfassung."""
    haushalt_id, akte_id = neue_akte(session)
    tag = eroeffnungstag(session, akte_id) + timedelta(days=3)
    hf = Bestandteil("hauptforderung", Bestandteilart.HAUPTFORDERUNG, D("10.00"), (), tag)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=hf)
    buchung = gegenbuchung(session, haushalt_id, "verbindlichkeiten.hauptforderung")
    assert buchung.art == "verbindlichkeiten.entstehung"


def test_ohne_entstehungstag_zuerst(session: Session) -> None:
    """E-35: Bestandteile ohne entstanden_am kommen in ihrer Gruppe zuerst."""
    haushalt_id, akte_id = neue_akte(session)
    mit = Bestandteil("a_kosten", Bestandteilart.KOSTEN_VERFAHREN, D("5.00"), (), T(2024, 1, 2))
    ohne = Bestandteil("z_kosten", Bestandteilart.KOSTEN_VERFAHREN, D("6.00"))
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=mit)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=ohne)
    inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
    assert [b.kennung for b in inhalt.bestandteile] == ["z_kosten", "a_kosten"]


def test_kennung_je_akte_eindeutig(session: Session) -> None:
    _, akte_id = neue_akte(session)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=HF)
    with pytest.raises(EingabeUngueltigError, match="Kennung"):
        lege_bestandteil_an(session, akte_id=akte_id, bestandteil=HF)


def test_zahlung_als_buchung_und_ereignis(session: Session) -> None:
    """Kap. 4.3: Zahlung, Soll Zahlungen, Haben Externe Mittel; dazu das Ereignis zahlung."""
    haushalt_id, akte_id = neue_akte(session)
    ereignis_id = erfasse_zahlung(
        session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("150.00"))
    )
    (zahlungen,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.zahlungen")
    (extern,) = konten_mit_rolle(session, haushalt_id, "kern.externe_mittel")
    assert saldo(session, konto_id=zahlungen.id, stichtag=T(2025, 2, 3)) == D("150.00")
    assert saldo(session, konto_id=extern.id, stichtag=T(2025, 2, 3)) == D("-150.00")
    zeile = session.get_one(EreignisZeile, ereignis_id)
    buchung = session.get_one(Buchung, zeile.buchung_id)
    assert (zeile.typ, zeile.datum) == ("zahlung", T(2025, 2, 3))
    assert (buchung.art, buchung.wertstellung) == ("verbindlichkeiten.zahlung", T(2025, 2, 3))


def test_zahlung_nicht_als_einfaches_ereignis(session: Session) -> None:
    _, akte_id = neue_akte(session)
    with pytest.raises(EingabeUngueltigError, match="erfasse_zahlung"):
        erfasse_ereignis(session, akte_id=akte_id, ereignis=Ereignis(E.ZAHLUNG, T(2025, 2, 3)))


def test_unbekannte_akte(session: Session) -> None:
    with pytest.raises(AkteUnbekanntError):
        erfasse_ereignis(
            session, akte_id=uuid.uuid4(), ereignis=Ereignis(E.ANERKENNTNIS, T(2025, 1, 1))
        )


# --- Laden --------------------------------------------------------------------------------------


def test_laden_liefert_die_eingaben_der_berechnung(session: Session) -> None:
    parameter = Aktenparameter(
        anrechnung=Anrechnungsregel.INDIVIDUELL,
        reihenfolge=(Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN, Gruppe.KOSTEN),
        tageszaehlung=Tageszaehlung.ACT_ACT,
        teilungstage=frozenset({T(2024, 9, 1)}),
    )
    haushalt_id, akte_id = neue_akte(
        session, parameter=parameter, verbraucherdarlehen=True, aktenzeichen_glaeubiger="AZ-1"
    )
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=HF)
    erfasse_zahlung(session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("150.00")))
    mahnbescheid = Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2024, 6, 3), gericht_land="HH")
    erfasse_ereignis(session, akte_id=akte_id, ereignis=mahnbescheid)
    eintragung = Ereignis(E.EINTRAGUNGSANORDNUNG, T(2024, 7, 1), bekanntgabe_am=T(2024, 7, 4))
    erfasse_ereignis(session, akte_id=akte_id, ereignis=eintragung)

    inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)

    assert inhalt.parameter == parameter
    assert inhalt.verbraucherdarlehen is True
    assert inhalt.haushalt_land == "SH"
    assert inhalt.kopf.aktenzeichen_glaeubiger == "AZ-1"
    assert inhalt.kopf.glaeubiger_name == "Muster Inkasso"
    assert inhalt.bestandteile == (HF,)
    assert inhalt.zahlungen == (Zahlung(T(2025, 2, 3), D("150.00")),)
    assert inhalt.ereignisse == (mahnbescheid, eintragung, Ereignis(E.ZAHLUNG, T(2025, 2, 3)))
    berechne(inhalt.parameter, inhalt.bestandteile, inhalt.zahlungen, T(2025, 6, 30), REIHE)


def test_versaeumnisurteil_bleibt_erhalten(session: Session) -> None:
    haushalt_id, akte_id = neue_akte(session)
    urteil = Ereignis(E.ZUSTELLUNG_URTEIL, T(2024, 6, 3), versaeumnisurteil=True)
    erfasse_ereignis(session, akte_id=akte_id, ereignis=urteil)
    assert lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id).ereignisse == (urteil,)


def test_zustellung_ohne_datum(session: Session) -> None:
    """Kap. 5.4: Fehlt bei einer Zustellung das Datum, warnt das System; gespeichert wird sie."""
    haushalt_id, akte_id = neue_akte(session)
    erfasse_ereignis(
        session, akte_id=akte_id, ereignis=Ereignis(E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, None)
    )
    erfasse_ereignis(session, akte_id=akte_id, ereignis=Ereignis(E.ANERKENNTNIS, T(2024, 1, 2)))
    ereignisse = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id).ereignisse
    assert [e.typ for e in ereignisse] == [E.ANERKENNTNIS, E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID]


def test_stornierte_zahlung_gilt_als_nie_geschehen(session: Session) -> None:
    """E-26: Ein Ereignis zahlung, dessen Buchung storniert ist, gilt als nie geschehen."""
    haushalt_id, akte_id = neue_akte(session)
    lege_bestandteil_an(session, akte_id=akte_id, bestandteil=HF)
    falsch = erfasse_zahlung(session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("15.00")))
    erfasse_zahlung(session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("150.00")))
    storniere_zahlung(session, akte_id=akte_id, ereignis_id=falsch)

    inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
    assert inhalt.zahlungen == (Zahlung(T(2025, 2, 3), D("150.00")),)
    assert inhalt.ereignisse == (Ereignis(E.ZAHLUNG, T(2025, 2, 3)),)
    (storniert,) = [e for e in inhalt.erfasst if e.id == falsch]
    assert storniert.storniert
    assert storniert.betrag == D("15.00")
    (zahlungen,) = konten_mit_rolle(session, haushalt_id, "verbindlichkeiten.zahlungen")
    assert saldo(session, konto_id=zahlungen.id, stichtag=T(2025, 2, 3)) == D("150.00")


def test_storno_nur_einmal(session: Session) -> None:
    _, akte_id = neue_akte(session)
    ereignis_id = erfasse_zahlung(
        session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("15.00"))
    )
    storniere_zahlung(session, akte_id=akte_id, ereignis_id=ereignis_id)
    with pytest.raises(StornoNichtMoeglichError):
        storniere_zahlung(session, akte_id=akte_id, ereignis_id=ereignis_id)


def test_storno_nur_bei_zahlungen(session: Session) -> None:
    _, akte_id = neue_akte(session)
    ereignis_id = erfasse_ereignis(
        session, akte_id=akte_id, ereignis=Ereignis(E.ANERKENNTNIS, T(2025, 1, 1))
    )
    with pytest.raises(EingabeUngueltigError, match="Zahlung"):
        storniere_zahlung(session, akte_id=akte_id, ereignis_id=ereignis_id)


def test_ereignis_loeschen(session: Session) -> None:
    haushalt_id, akte_id = neue_akte(session)
    ereignis_id = erfasse_ereignis(
        session, akte_id=akte_id, ereignis=Ereignis(E.ANERKENNTNIS, T(2025, 1, 1))
    )
    loesche_ereignis(session, akte_id=akte_id, ereignis_id=ereignis_id)
    assert lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id).ereignisse == ()


def test_zahlung_wird_nicht_geloescht_sondern_storniert(session: Session) -> None:
    _, akte_id = neue_akte(session)
    ereignis_id = erfasse_zahlung(
        session, akte_id=akte_id, zahlung=Zahlung(T(2025, 2, 3), D("15.00"))
    )
    with pytest.raises(EingabeUngueltigError, match="storniert"):
        loesche_ereignis(session, akte_id=akte_id, ereignis_id=ereignis_id)


def test_ereignis_einer_anderen_akte(session: Session) -> None:
    _, akte_a = neue_akte(session)
    _, akte_b = neue_akte(session)
    ereignis_id = erfasse_ereignis(
        session, akte_id=akte_a, ereignis=Ereignis(E.ANERKENNTNIS, T(2025, 1, 1))
    )
    with pytest.raises(EreignisUnbekanntError):
        loesche_ereignis(session, akte_id=akte_b, ereignis_id=ereignis_id)


def test_akte_eines_anderen_haushalts_ist_unbekannt(session: Session) -> None:
    _, akte_id = neue_akte(session)
    with pytest.raises(AkteUnbekanntError):
        lade_akte(session, haushalt_id=haushalt(session), akte_id=akte_id)


def test_aktenliste_des_haushalts(session: Session) -> None:
    haushalt_id, akte_a = neue_akte(session, aktenzeichen_glaeubiger="A-1")
    glaeubiger_id = lege_glaeubiger_an(session, haushalt_id=haushalt_id, name="Beispiel AG")
    akte_b = lege_akte_an(session, haushalt_id=haushalt_id, glaeubiger_id=glaeubiger_id)
    neue_akte(session)  # anderer Haushalt
    liste = akten(session, haushalt_id=haushalt_id)
    assert {(k.id, k.glaeubiger_name) for k in liste} == {
        (akte_a, "Muster Inkasso"),
        (akte_b, "Beispiel AG"),
    }


REIHE = lade_basiszinsreihe()
