# SPDX-License-Identifier: AGPL-3.0-or-later
"""Konten anlegen, buchen, stornieren (Fachkonzept 4.1 bis 4.4).

Die Funktionen prüfen vorab und liefern verständliche Fehler. Maßgeblich bleibt die
Datenbank: Sie erzwingt dieselben Regeln, spätestens am Ende der Transaktion. Keine Funktion
committet; das entscheidet der Aufrufer.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kern.geld import speicherbar
from app.kern.haushalt import Haushalt
from app.kern.ledger.fehler import (
    BuchungUnbekanntError,
    BuchungUngueltigError,
    HaushaltUnbekanntError,
    KontoUnbekanntError,
    KontoUngueltigError,
    StornoNichtMoeglichError,
)
from app.kern.ledger.modelle import (
    KONTOARTEN,
    NAMENSMUSTER,
    STORNO,
    Buchung,
    Konto,
    Kontoart,
    Posting,
)

_NAME = re.compile(NAMENSMUSTER)


@dataclass(frozen=True, slots=True)
class PostingEingabe:
    """Ein Posting eines Buchungsentwurfs. Soll positiv, Haben negativ (Kap. 4.1)."""

    konto_id: uuid.UUID
    betrag: Decimal


def _ist_name(wert: str) -> bool:
    """``<modul>.<name>`` (E-17); ``fullmatch``, damit kein Zeilenumbruch am Ende durchrutscht."""
    return _NAME.fullmatch(wert) is not None


def pruefe_konto(kontoart: Kontoart, rolle: str) -> None:
    """Kontoart ist eine der fünf Grundarten, die Rolle folgt dem Schema (Kap. 4.2)."""
    if kontoart not in KONTOARTEN:
        msg = f"Unbekannte Kontoart; zulässig sind {', '.join(KONTOARTEN)}."
        raise KontoUngueltigError(msg)
    if not _ist_name(rolle):
        msg = "Rolle muss die Form <modul>.<name> haben (Kleinbuchstaben, Unterstrich)."
        raise KontoUngueltigError(msg)


def pruefe_buchungsentwurf(
    art: str, wertstellung: date, postings: Sequence[PostingEingabe]
) -> None:
    """Regeln aus Kap. 3 und 4.4, soweit sie ohne Datenbank prüfbar sind.

    Raises:
        TypeError: wenn die Wertstellung kein ``date`` oder ein Betrag kein ``Decimal`` ist.
        BuchungUngueltigError: wenn eine Regel verletzt ist.
    """
    if not _ist_name(art):
        msg = "Art muss die Form <modul>.<name> haben (Kleinbuchstaben, Unterstrich)."
        raise BuchungUngueltigError(msg)
    if art == STORNO:
        msg = f"Die Art {STORNO} entsteht nur über storniere()."
        raise BuchungUngueltigError(msg)
    # datetime ist eine Unterklasse von date, aber kein fachliches Datum (CLAUDE.md).
    if type(wertstellung) is not date:
        msg = "Wertstellung muss ein datetime.date sein."
        raise TypeError(msg)
    if len(postings) < 2:
        msg = "Eine Buchung braucht mindestens zwei Postings."
        raise BuchungUngueltigError(msg)
    if len({posting.konto_id for posting in postings}) < 2:
        msg = "Eine Buchung bebucht mindestens zwei verschiedene Konten."
        raise BuchungUngueltigError(msg)
    summe = Decimal(0)
    for posting in postings:
        try:
            betrag = speicherbar(posting.betrag)
        except ValueError as fehler:
            raise BuchungUngueltigError(str(fehler)) from fehler
        if betrag == 0:
            msg = "Ein Posting mit dem Betrag null ist nicht zulässig."
            raise BuchungUngueltigError(msg)
        summe += betrag
    if summe != 0:
        msg = "Die Summe der Postings einer Buchung muss null sein."
        raise BuchungUngueltigError(msg)


def lege_konto_an(
    session: Session, *, haushalt_id: uuid.UUID, kontoart: Kontoart, rolle: str, bezeichnung: str
) -> Konto:
    """Konto anlegen und in die Datenbank schreiben (ohne Commit)."""
    pruefe_konto(kontoart, rolle)
    if session.get(Haushalt, haushalt_id) is None:
        raise HaushaltUnbekanntError(str(haushalt_id))
    konto = Konto(haushalt_id=haushalt_id, kontoart=kontoart, rolle=rolle, bezeichnung=bezeichnung)
    session.add(konto)
    session.flush()
    return konto


def buche(
    session: Session,
    *,
    haushalt_id: uuid.UUID,
    art: str,
    wertstellung: date,
    postings: Sequence[PostingEingabe],
    text: str | None = None,
) -> Buchung:
    """Buchung mit ihren Postings schreiben (ohne Commit).

    Buchung und Postings gehen in getrennten Anweisungen an die Datenbank: Postings
    entstehen nur in der Transaktion ihrer Buchung, und die Datenbank erkennt eine neue
    Buchung erst nach deren INSERT (Kap. 4.4).
    """
    pruefe_buchungsentwurf(art, wertstellung, postings)
    if session.get(Haushalt, haushalt_id) is None:
        raise HaushaltUnbekanntError(str(haushalt_id))
    konto_ids = {posting.konto_id for posting in postings}
    haushalte = dict(
        session.execute(select(Konto.id, Konto.haushalt_id).where(Konto.id.in_(konto_ids))).all()
    )
    if fehlend := konto_ids - haushalte.keys():
        raise KontoUnbekanntError(", ".join(sorted(str(konto_id) for konto_id in fehlend)))
    if any(konto_haushalt != haushalt_id for konto_haushalt in haushalte.values()):
        msg = "Alle Konten einer Buchung gehören zum Haushalt der Buchung."
        raise BuchungUngueltigError(msg)
    return _schreibe(session, haushalt_id, art, wertstellung, postings, None, text)


def storniere(session: Session, *, buchung_id: uuid.UUID, text: str | None = None) -> Buchung:
    """Stornobuchung zu ``buchung_id`` schreiben (ohne Commit).

    Das Storno besteht genau aus den negierten Postings und trägt die Wertstellung der
    Ursprungsbuchung (E-18); wann storniert wurde, steht in ``erfasst_am``.
    """
    original = session.get(Buchung, buchung_id)
    if original is None:
        raise BuchungUnbekanntError(str(buchung_id))
    if original.storno_von is not None:
        msg = "Ein Storno wird nicht storniert; die Korrektur ist eine Neubuchung."
        raise StornoNichtMoeglichError(msg)
    if session.scalar(select(Buchung.id).where(Buchung.storno_von == buchung_id)) is not None:
        msg = "Die Buchung ist bereits storniert."
        raise StornoNichtMoeglichError(msg)
    gegenpostings = [
        PostingEingabe(posting.konto_id, -posting.betrag)
        for posting in session.scalars(select(Posting).where(Posting.buchung_id == buchung_id))
    ]
    return _schreibe(
        session,
        original.haushalt_id,
        STORNO,
        original.wertstellung,
        gegenpostings,
        original.id,
        text,
    )


def _schreibe(
    session: Session,
    haushalt_id: uuid.UUID,
    art: str,
    wertstellung: date,
    postings: Sequence[PostingEingabe],
    storno_von: uuid.UUID | None,
    text: str | None,
) -> Buchung:
    buchung = Buchung(
        haushalt_id=haushalt_id,
        art=art,
        wertstellung=wertstellung,
        storno_von=storno_von,
        text=text,
    )
    session.add(buchung)
    session.flush()
    session.add_all(
        Posting(buchung_id=buchung.id, konto_id=posting.konto_id, betrag=posting.betrag)
        for posting in postings
    )
    session.flush()
    return buchung
