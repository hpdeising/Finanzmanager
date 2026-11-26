# SPDX-License-Identifier: AGPL-3.0-or-later
"""Importläufe speichern, Duplikate erkennen, Zeilen als gebucht markieren (Kap. 8).

Ablauf nach Kap. 8: Datei hochladen (``importiere``), Zahlungskandidaten erkennen, Duplikate
erkennen (``kandidaten``), Zuordnungsvorschlag und Bestätigung im Modul. Erst nach der
Bestätigung bucht das Modul je Akte eine Zahlung und meldet die Buchungen mit
``markiere_gebucht`` zurück. ``schliesse_ab`` verwirft danach alle Zeilen ohne Buchung
(Datenminimierung). Ohne Bestätigung wird nichts gebucht; der Kern bucht selbst nie.

Keine Funktion committet; das entscheidet der Aufrufer. Meldungen nennen nie Werte aus der
Datei (CLAUDE.md, Datenschutz).
"""

import codecs
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.kern.import_.camt053 import lies_camt053
from app.kern.import_.csv_profil import CsvProfil, lies_csv
from app.kern.import_.modelle import (
    GEBUCHT_EINDEUTIG,
    CsvProfilZeile,
    Format,
    ImportLauf,
    ImportZeile,
    ImportZeileBuchung,
    Zeilenstatus,
)
from app.kern.import_.umsatz import (
    ImportUngueltigError,
    Umsatz,
    WertstellungAus,
    duplikat_schluessel,
    iban_normiert,
    wertstellung,
)
from app.kern.ledger import EXTERNE_MITTEL, STORNO, Buchung, Konto, Posting


class ProfilUnbekanntError(LookupError):
    """Das CSV-Profil gibt es im Haushalt nicht."""


class ProfilUngueltigError(ValueError):
    """Das CSV-Profil ist ungültig."""


class ProfilVorhandenError(ProfilUngueltigError):
    """Ein CSV-Profil mit diesem Namen gibt es im Haushalt schon."""


class LaufUnbekanntError(LookupError):
    """Den Importlauf gibt es im Haushalt nicht."""


class ZeileUnbekanntError(LookupError):
    """Die Importzeile gibt es im Haushalt nicht."""


class LaufAbgeschlossenError(ValueError):
    """Der Importlauf ist abgeschlossen und nimmt keine Buchung mehr an."""


class ZeileNichtBuchbarError(ValueError):
    """Die Zeile lässt sich nicht als gebucht markieren; die Meldung nennt den Grund."""


@dataclass(frozen=True, slots=True)
class Kandidat:
    """Zeile eines Laufs mit dem Ergebnis der Duplikaterkennung (Kap. 8, Schritt 3)."""

    zeile: ImportZeile
    duplikat: bool


# --- CSV-Profile ------------------------------------------------------------------------------


def speichere_profil(session: Session, *, haushalt_id: uuid.UUID, profil: CsvProfil) -> uuid.UUID:
    """CSV-Profil für den Haushalt speichern; liefert seine ID.

    Raises:
        ProfilVorhandenError: wenn der Name im Haushalt schon vergeben ist.
        ProfilUngueltigError: bei unbekannter Kodierung oder Trennzeichen, die nicht genau ein
            Zeichen sind.
    """
    _pruefe_profil(profil)
    vorhanden = session.scalar(
        select(CsvProfilZeile.id).where(
            CsvProfilZeile.haushalt_id == haushalt_id, CsvProfilZeile.name == profil.name
        )
    )
    if vorhanden is not None:
        msg = "Ein CSV-Profil mit diesem Namen gibt es schon."
        raise ProfilVorhandenError(msg)
    zeile = CsvProfilZeile(
        haushalt_id=haushalt_id,
        name=profil.name,
        spalte_buchungstag=profil.spalte_buchungstag,
        spalte_betrag=profil.spalte_betrag,
        spalten_verwendungszweck=list(profil.spalten_verwendungszweck),
        spalte_valuta=profil.spalte_valuta,
        spalte_gegen_name=profil.spalte_gegen_name,
        spalte_gegen_iban=profil.spalte_gegen_iban,
        trennzeichen=profil.trennzeichen,
        kodierung=profil.kodierung,
        datumsformat=profil.datumsformat,
        dezimaltrennzeichen=profil.dezimaltrennzeichen,
        tausendertrennzeichen=profil.tausendertrennzeichen,
        kopfzeilen_ueberspringen=profil.kopfzeilen_ueberspringen,
    )
    session.add(zeile)
    session.flush()
    return zeile.id


def _pruefe_profil(profil: CsvProfil) -> None:
    if not profil.name.strip():
        msg = "Ein CSV-Profil braucht einen Namen."
        raise ProfilUngueltigError(msg)
    einzeln = [profil.trennzeichen, profil.dezimaltrennzeichen]
    if profil.tausendertrennzeichen is not None:
        einzeln.append(profil.tausendertrennzeichen)
    if any(len(zeichen) != 1 for zeichen in einzeln):
        msg = "Trennzeichen sind genau ein Zeichen."
        raise ProfilUngueltigError(msg)
    if profil.kopfzeilen_ueberspringen < 0:
        msg = "Die Zahl der übersprungenen Kopfzeilen ist nicht negativ."
        raise ProfilUngueltigError(msg)
    try:
        codecs.lookup(profil.kodierung)
    except LookupError as fehler:
        msg = "Unbekannte Kodierung."
        raise ProfilUngueltigError(msg) from fehler


def profile(session: Session, haushalt_id: uuid.UUID) -> list[tuple[uuid.UUID, CsvProfil]]:
    """CSV-Profile des Haushalts mit ihrer ID, nach Namen sortiert."""
    zeilen = session.scalars(
        select(CsvProfilZeile)
        .where(CsvProfilZeile.haushalt_id == haushalt_id)
        .order_by(CsvProfilZeile.name)
    ).all()
    return [(zeile.id, _als_profil(zeile)) for zeile in zeilen]


def profil(session: Session, haushalt_id: uuid.UUID, profil_id: uuid.UUID) -> CsvProfil:
    """Ein CSV-Profil des Haushalts.

    Raises:
        ProfilUnbekanntError: wenn es das Profil im Haushalt nicht gibt.
    """
    zeile = session.get(CsvProfilZeile, profil_id)
    if zeile is None or zeile.haushalt_id != haushalt_id:
        raise ProfilUnbekanntError(str(profil_id))
    return _als_profil(zeile)


def loesche_profil(session: Session, haushalt_id: uuid.UUID, profil_id: uuid.UUID) -> None:
    """CSV-Profil löschen; Läufe behalten den Namen des Profils.

    Raises:
        ProfilUnbekanntError: wenn es das Profil im Haushalt nicht gibt.
    """
    zeile = session.get(CsvProfilZeile, profil_id)
    if zeile is None or zeile.haushalt_id != haushalt_id:
        raise ProfilUnbekanntError(str(profil_id))
    session.delete(zeile)
    session.flush()


def _als_profil(zeile: CsvProfilZeile) -> CsvProfil:
    return CsvProfil(
        name=zeile.name,
        spalte_buchungstag=zeile.spalte_buchungstag,
        spalte_betrag=zeile.spalte_betrag,
        spalten_verwendungszweck=tuple(zeile.spalten_verwendungszweck),
        spalte_valuta=zeile.spalte_valuta,
        spalte_gegen_name=zeile.spalte_gegen_name,
        spalte_gegen_iban=zeile.spalte_gegen_iban,
        trennzeichen=zeile.trennzeichen,
        kodierung=zeile.kodierung,
        datumsformat=zeile.datumsformat,
        dezimaltrennzeichen=zeile.dezimaltrennzeichen,
        tausendertrennzeichen=zeile.tausendertrennzeichen,
        kopfzeilen_ueberspringen=zeile.kopfzeilen_ueberspringen,
    )


# --- Läufe ------------------------------------------------------------------------------------


def lies_datei(daten: bytes, dateiformat: Format, profil: CsvProfil | None) -> list[Umsatz]:
    """Umsätze einer Datei; ein CSV braucht ein Profil, CAMT.053 keins.

    Raises:
        ImportUngueltigError: wenn sich die Datei nicht lesen lässt oder das Profil nicht passt.
    """
    if dateiformat is Format.CSV:
        if profil is None:
            msg = "Ein CSV-Import braucht ein Profil."
            raise ImportUngueltigError(msg)
        return lies_csv(daten, profil)
    if profil is not None:
        msg = "Ein CAMT.053-Import nutzt kein CSV-Profil."
        raise ImportUngueltigError(msg)
    return lies_camt053(daten)


def importiere(
    session: Session,
    *,
    haushalt_id: uuid.UUID,
    umsaetze: Sequence[Umsatz],
    dateiformat: Format,
    profil_name: str | None,
    wertstellung_aus: WertstellungAus,
) -> ImportLauf:
    """Lauf anlegen und seine Zahlungskandidaten speichern (Kap. 8, Schritte 1 bis 3).

    Gespeichert werden nur Kandidaten, also Belastungen, die keine Rückbuchung sind;
    Gutschriften und Rückbuchungen nie (Datenminimierung). Die Wertstellung folgt der
    Einstellung zu P-16.

    Raises:
        ImportUngueltigError: wenn bei einem Kandidaten das gewählte Datum fehlt. Dann wird
            nichts gespeichert; es wird nicht geschätzt.
    """
    if (dateiformat is Format.CSV) != (profil_name is not None):
        msg = "Den Namen eines Profils hat genau ein CSV-Import."
        raise ImportUngueltigError(msg)
    kandidaten = [umsatz for umsatz in umsaetze if umsatz.ist_kandidat]
    daten: list[date] = []
    for nummer, umsatz in enumerate(kandidaten, start=1):
        try:
            daten.append(wertstellung(umsatz, wertstellung_aus))
        except ImportUngueltigError as fehler:
            msg = f"Belastung Nr. {nummer}: {fehler}"
            raise ImportUngueltigError(msg) from fehler
    lauf = ImportLauf(
        haushalt_id=haushalt_id,
        format=dateiformat.value,
        profil_name=profil_name,
        wertstellung_aus=wertstellung_aus.value,
        umsaetze_gelesen=len(umsaetze),
    )
    session.add(lauf)
    session.flush()
    for position, (umsatz, datum) in enumerate(zip(kandidaten, daten, strict=True), start=1):
        session.add(
            ImportZeile(
                lauf_id=lauf.id,
                haushalt_id=haushalt_id,
                position=position,
                datum=datum,
                buchungstag=umsatz.buchungstag,
                valuta=umsatz.valuta,
                betrag=umsatz.betrag,
                gegen_name=umsatz.gegen_name,
                gegen_iban=iban_normiert(umsatz.gegen_iban),
                verwendungszweck=umsatz.verwendungszweck,
                schluessel=duplikat_schluessel(umsatz, datum),
            )
        )
    session.flush()
    return lauf


def laeufe(session: Session, haushalt_id: uuid.UUID) -> list[ImportLauf]:
    """Läufe des Haushalts, der neueste zuerst."""
    return list(
        session.scalars(
            select(ImportLauf)
            .where(ImportLauf.haushalt_id == haushalt_id)
            .order_by(ImportLauf.angelegt_am.desc(), ImportLauf.id)
        ).all()
    )


def lauf(session: Session, haushalt_id: uuid.UUID, lauf_id: uuid.UUID) -> ImportLauf:
    """Ein Lauf des Haushalts.

    Raises:
        LaufUnbekanntError: wenn es den Lauf im Haushalt nicht gibt.
    """
    gefunden = session.get(ImportLauf, lauf_id)
    if gefunden is None or gefunden.haushalt_id != haushalt_id:
        raise LaufUnbekanntError(str(lauf_id))
    return gefunden


def kandidaten(session: Session, lauf: ImportLauf) -> list[Kandidat]:
    """Zeilen eines Laufs in der Reihenfolge der Datei, mit Duplikaterkennung (Kap. 8).

    Eine offene Zeile ist ein Duplikat, wenn ihr Schlüssel im Haushalt schon gebucht ist oder
    eine frühere Zeile desselben Laufs denselben Schlüssel hat. Das Ergebnis wird berechnet,
    nicht gespeichert: Es ändert sich, sobald eine andere Zeile gebucht wird.
    """
    andere = aliased(ImportZeile)
    gebucht = exists().where(
        andere.haushalt_id == ImportZeile.haushalt_id,
        andere.schluessel == ImportZeile.schluessel,
        andere.status == Zeilenstatus.GEBUCHT.value,
    )
    frueher = exists().where(
        andere.lauf_id == ImportZeile.lauf_id,
        andere.schluessel == ImportZeile.schluessel,
        andere.position < ImportZeile.position,
    )
    zeilen = session.execute(
        select(ImportZeile, ImportZeile.status == Zeilenstatus.OFFEN.value, gebucht | frueher)
        .where(ImportZeile.lauf_id == lauf.id)
        .order_by(ImportZeile.position)
    ).all()
    return [Kandidat(zeile, offen and doppelt) for zeile, offen, doppelt in zeilen]


def schliesse_ab(session: Session, haushalt_id: uuid.UUID, lauf_id: uuid.UUID) -> ImportLauf:
    """Lauf abschließen: Zeilen ohne Buchung verwerfen (Kap. 8, Datenminimierung).

    Ein schon abgeschlossener Lauf bleibt unverändert.

    Raises:
        LaufUnbekanntError: wenn es den Lauf im Haushalt nicht gibt.
    """
    gesperrt = _gesperrter_lauf(session, haushalt_id, lauf_id)
    if gesperrt.abgeschlossen_am is not None:
        return gesperrt
    session.execute(
        delete(ImportZeile).where(
            ImportZeile.lauf_id == lauf_id, ImportZeile.status == Zeilenstatus.OFFEN.value
        )
    )
    session.execute(
        update(ImportLauf).where(ImportLauf.id == lauf_id).values(abgeschlossen_am=func.now())
    )
    session.refresh(gesperrt)
    return gesperrt


def _gesperrter_lauf(session: Session, haushalt_id: uuid.UUID, lauf_id: uuid.UUID) -> ImportLauf:
    gefunden = session.scalars(
        select(ImportLauf)
        .where(ImportLauf.id == lauf_id, ImportLauf.haushalt_id == haushalt_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if gefunden is None:
        raise LaufUnbekanntError(str(lauf_id))
    return gefunden


# --- Buchungen einer Zeile --------------------------------------------------------------------


def markiere_gebucht(
    session: Session,
    *,
    haushalt_id: uuid.UUID,
    zeile_id: uuid.UUID,
    buchung_ids: Sequence[uuid.UUID],
) -> None:
    """Zeile als gebucht markieren und mit ihren Buchungen verknüpfen (Kap. 8, Schritt 6).

    Das Modul bucht nach der Bestätigung je Akte eine Zahlung und ruft dann diese Funktion
    auf. Der Kern prüft, dass die Buchungen zur Zeile passen: gleicher Haushalt, Wertstellung
    gleich dem Datum der Zeile, keine Stornos, nicht storniert, nicht schon mit einer Zeile
    verknüpft, und zusammen fließt genau der Betrag der Zeile aus den externen Mitteln ab
    (Kap. 4.3).

    Raises:
        ZeileUnbekanntError: wenn es die Zeile im Haushalt nicht gibt.
        LaufAbgeschlossenError: wenn ihr Lauf abgeschlossen ist.
        ZeileNichtBuchbarError: wenn die Zeile gebucht oder ein Duplikat ist oder die
            Buchungen nicht zu ihr passen.
    """
    zeile = session.get(ImportZeile, zeile_id)
    if zeile is None or zeile.haushalt_id != haushalt_id:
        raise ZeileUnbekanntError(str(zeile_id))
    lauf_der_zeile = _gesperrter_lauf(session, haushalt_id, zeile.lauf_id)
    if lauf_der_zeile.abgeschlossen_am is not None:
        msg = "Der Importlauf ist abgeschlossen."
        raise LaufAbgeschlossenError(msg)
    zeile = session.scalars(
        select(ImportZeile)
        .where(ImportZeile.id == zeile_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if zeile.status != Zeilenstatus.OFFEN.value:
        msg = "Die Zeile ist schon gebucht."
        raise ZeileNichtBuchbarError(msg)
    if next(k.duplikat for k in kandidaten(session, lauf_der_zeile) if k.zeile.id == zeile.id):
        msg = "Die Zeile ist ein Duplikat (Fachkonzept 8, Schritt 3)."
        raise ZeileNichtBuchbarError(msg)
    _pruefe_buchungen(session, zeile, buchung_ids)
    try:
        with session.begin_nested():
            zeile.status = Zeilenstatus.GEBUCHT.value
            session.add_all(
                ImportZeileBuchung(zeile_id=zeile.id, buchung_id=buchung_id)
                for buchung_id in buchung_ids
            )
            session.flush()
    except IntegrityError as fehler:
        if _constraint(fehler) != GEBUCHT_EINDEUTIG:
            raise
        msg = "Die Zeile ist ein Duplikat (Fachkonzept 8, Schritt 3)."
        raise ZeileNichtBuchbarError(msg) from fehler


def _pruefe_buchungen(
    session: Session, zeile: ImportZeile, buchung_ids: Sequence[uuid.UUID]
) -> None:
    if not buchung_ids:
        msg = "Eine gebuchte Zeile hat mindestens eine Buchung."
        raise ZeileNichtBuchbarError(msg)
    if len(set(buchung_ids)) != len(buchung_ids):
        msg = "Eine Buchung ist mehrfach genannt."
        raise ZeileNichtBuchbarError(msg)
    buchungen = session.scalars(select(Buchung).where(Buchung.id.in_(buchung_ids))).all()
    if len(buchungen) != len(buchung_ids) or any(
        b.haushalt_id != zeile.haushalt_id for b in buchungen
    ):
        msg = "Eine Buchung gibt es im Haushalt nicht."
        raise ZeileNichtBuchbarError(msg)
    if any(b.art == STORNO for b in buchungen):
        msg = "Ein Storno stammt nie aus einem Import."
        raise ZeileNichtBuchbarError(msg)
    if any(b.wertstellung != zeile.datum for b in buchungen):
        msg = "Die Wertstellung einer Buchung weicht vom Datum der Zeile ab."
        raise ZeileNichtBuchbarError(msg)
    storno = aliased(Buchung)
    if session.scalar(select(exists().where(storno.storno_von.in_(buchung_ids)))):
        msg = "Eine Buchung ist storniert."
        raise ZeileNichtBuchbarError(msg)
    if session.scalar(select(exists().where(ImportZeileBuchung.buchung_id.in_(buchung_ids)))):
        msg = "Eine Buchung stammt schon aus einer anderen Zeile."
        raise ZeileNichtBuchbarError(msg)
    abfluss = session.scalar(
        select(func.coalesce(func.sum(Posting.betrag), Decimal(0)))
        .join(Konto, Konto.id == Posting.konto_id)
        .where(Posting.buchung_id.in_(buchung_ids), Konto.rolle == EXTERNE_MITTEL)
    )
    if abfluss != -zeile.betrag:
        msg = "Die Buchungen bewegen nicht genau den Betrag der Zeile aus den externen Mitteln."
        raise ZeileNichtBuchbarError(msg)


def _constraint(fehler: IntegrityError) -> str | None:
    diag = getattr(fehler.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None
