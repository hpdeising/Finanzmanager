# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kontosperre (Fachkonzept 4.4, E-27).

Der Kern sperrt Konten bis zu einem Datum. Er kennt dabei weder Akte noch Festschreibung,
nur Konto und Datum (E-17); wann gesperrt wird, entscheidet ein Modul. Ein Posting auf ein
gesperrtes Konto, dessen Buchung ein Buchungsdatum am oder vor dem Sperrdatum hat, lehnt die
Datenbank ab.

Nebenläufigkeit: Jedes Posting hält sein Konto gemeinsam mit anderen Postings, eine Sperre
hält es allein, jeweils bis zum Ende der Transaktion. Wer das Konto nicht bekommt, scheitert
sofort; die API meldet das als ``KontoBelegtError``. Postings und Sperren gibt es nur in
READ COMMITTED, der Standardstufe der Anwendung (Migration 0002).
"""

import uuid
from collections.abc import Collection, Generator
from contextlib import contextmanager
from datetime import date
from typing import Final

import psycopg
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.ledger.fehler import (
    KontoBelegtError,
    KontoGesperrtError,
    KontoUnbekanntError,
    SperreUngueltigError,
)
from app.kern.ledger.modelle import Konto, KontoSperre

# Regeln aus Migration 0002, an denen die Datenbank mit 55P03 sofort abbricht.
_BELEGT: Final = {
    "konto_wird_gesperrt": "Das Konto wird gerade gesperrt; bitte erneut versuchen.",
    "konto_wird_bebucht": "Auf dem Konto wird gerade gebucht; bitte erneut versuchen.",
}


def _regel(fehler: DBAPIError) -> tuple[str | None, str | None]:
    ursprung = fehler.orig
    if isinstance(ursprung, psycopg.Error):
        return ursprung.sqlstate, ursprung.diag.constraint_name
    return None, None


@contextmanager
def uebersetze_sperrfehler() -> Generator[None]:
    """Fehler der Kontosperre aus der Datenbank in Fehler des Kerns übersetzen.

    Die Meldungen nennen weder Konto noch Betrag (CLAUDE.md, Sicherheit). Andere Fehler
    reicht der Block unverändert durch.
    """
    try:
        yield
    except DBAPIError as fehler:
        zustand, regel = _regel(fehler)
        if zustand == "55P03" and regel in _BELEGT:
            raise KontoBelegtError(_BELEGT[regel]) from fehler
        if regel == "posting_konto_gesperrt":
            msg = "Ein Konto der Buchung ist gesperrt; das Buchungsdatum muss danach liegen."
            raise KontoGesperrtError(msg) from fehler
        if regel == "konto_sperre_steigt":
            msg = "Das Sperrdatum eines Kontos steigt nur."
            raise SperreUngueltigError(msg) from fehler
        raise


def _pruefe_konten(session: Session, konto_ids: Collection[uuid.UUID]) -> None:
    vorhanden = set(session.scalars(select(Konto.id).where(Konto.id.in_(konto_ids))))
    if fehlend := set(konto_ids) - vorhanden:
        raise KontoUnbekanntError(", ".join(sorted(str(konto_id) for konto_id in fehlend)))


def sperrdaten(session: Session, konto_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, date]:
    """Sperrdatum je gesperrtem Konto; ungesperrte Konten fehlen im Ergebnis."""
    abfrage = (
        select(KontoSperre.konto_id, func.max(KontoSperre.gesperrt_bis))
        .where(KontoSperre.konto_id.in_(konto_ids))
        .group_by(KontoSperre.konto_id)
    )
    return dict(session.execute(abfrage).all())


def sperrdatum(session: Session, *, konto_id: uuid.UUID) -> date | None:
    """Bis einschließlich wann ``konto_id`` gesperrt ist; ``None`` ohne Sperre."""
    _pruefe_konten(session, {konto_id})
    return sperrdaten(session, {konto_id}).get(konto_id)


def halte_konten(session: Session, *, konto_ids: Collection[uuid.UUID]) -> None:
    """Konten bis zum Ende der Transaktion allein halten (ohne Commit).

    Danach bucht keine andere Transaktion mehr auf ihnen, bis diese endet. Eine
    Festschreibung ruft das auf, bevor sie rechnet; so rechnet sie auf genau den Postings,
    die ihre Sperre einfriert (Fachkonzept 5.2 Schritt 7). Läuft gerade eine Buchung auf
    einem der Konten, scheitert der Aufruf sofort.

    Raises:
        KontoUnbekanntError: wenn ein Konto fehlt.
        KontoBelegtError: wenn eine andere Transaktion auf einem der Konten bucht oder es hält.
    """
    reihenfolge = sorted(set(konto_ids))
    _pruefe_konten(session, reihenfolge)
    with uebersetze_sperrfehler():
        for konto_id in reihenfolge:
            session.execute(select(func.public.ledger_halte_konto(konto_id)))


def sperre_konten(session: Session, *, konto_ids: Collection[uuid.UUID], bis: date) -> None:
    """Konten bis einschließlich ``bis`` sperren (ohne Commit).

    Das Sperrdatum eines Kontos steigt nur. Die Konten werden zuerst gehalten
    (``halte_konten``), dann wird das bisherige Sperrdatum gelesen und die Sperre geschrieben.

    Raises:
        TypeError: wenn ``bis`` kein ``date`` ist.
        KontoUnbekanntError: wenn ein Konto fehlt.
        SperreUngueltigError: wenn ``bis`` nicht nach dem bisherigen Sperrdatum liegt.
        KontoBelegtError: wenn eine andere Transaktion auf einem der Konten bucht oder es hält.
    """
    # datetime ist eine Unterklasse von date, aber kein fachliches Datum (CLAUDE.md).
    if type(bis) is not date:
        msg = "Sperrdatum muss ein datetime.date sein."
        raise TypeError(msg)
    reihenfolge = sorted(set(konto_ids))
    halte_konten(session, konto_ids=reihenfolge)
    bisher = sperrdaten(session, reihenfolge)
    if any(bis <= datum for datum in bisher.values()):
        msg = f"Das Sperrdatum eines Kontos steigt nur; bisher bis {max(bisher.values())}."
        raise SperreUngueltigError(msg)
    with uebersetze_sperrfehler():
        session.add_all(
            KontoSperre(konto_id=konto_id, gesperrt_bis=bis) for konto_id in reihenfolge
        )
        session.flush()
