# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabellen des Moduls Verbindlichkeiten (Fachkonzept Kap. 4.2, 4.3 und 4.5).

Die Tabellen des Moduls verweisen auf Kern-Tabellen, nie umgekehrt (E-17). Eine Zahlung ist
keine eigene Tabelle: Sie ist eine Buchung ``verbindlichkeiten.zahlung`` auf dem Zahlungskonto
der Akte (Kap. 4.3) und ein Ereignis ``zahlung``, das auf diese Buchung verweist (Kap. 4.5).
Auch der Ursprungsbetrag eines Bestandteils steht zusätzlich als Buchung
``verbindlichkeiten.entstehung`` im Ledger.

Der Status einer Akte hat keine Spalte; er wird berechnet (E-38).

Die CHECKs der Aufzählungen entstehen aus den Aufzählungen der Domain; die Migration nennt
dieselben Werte wörtlich, weil eine gemergte Migration sich nie ändert.
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.kern.db import Basis, BetragTyp
from app.module.verbindlichkeiten.domain import (
    Anrechnungsregel,
    Bestandteilart,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zinsbeginn,
    Zinsregeltyp,
)

RICHTUNGEN: Final = ("verbindlichkeit", "forderung")
QUELLEN_ZINSREGEL: Final = ("titel", "vertrag")


def werte_in(spalte: str, werte: Iterable[str]) -> str:
    """CHECK-Ausdruck ``spalte IN ('a', 'b', …)``; die Werte sind feste Bezeichner ohne '."""
    liste = ", ".join(f"'{wert}'" for wert in werte)
    return f"{spalte} IN ({liste})"


def _aufzaehlung(spalte: str, aufzaehlung: type[StrEnum]) -> str:
    return werte_in(spalte, (wert.value for wert in aufzaehlung))


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


class Glaeubiger(Basis):
    """Gläubiger einer Akte (Kap. 4.5); vorerst nur Name und Kontaktangaben als Text."""

    __tablename__ = "glaeubiger"
    __table_args__ = (CheckConstraint("name <> ''", name="name_nicht_leer"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    anschrift: Mapped[str | None] = mapped_column(Text)
    iban: Mapped[str | None] = mapped_column(Text)
    vertreter: Mapped[str | None] = mapped_column(Text)
    kontakt: Mapped[str | None] = mapped_column(Text)


class Akte(Basis):
    """Akte mit ihren Rechenvorgaben (Kap. 4.5, 5.1); Voreinstellungen wie in Kap. 5.1."""

    __tablename__ = "akte"
    __table_args__ = (
        CheckConstraint(werte_in("richtung", RICHTUNGEN), name="richtung"),
        CheckConstraint(_aufzaehlung("anrechnung", Anrechnungsregel), name="anrechnung"),
        CheckConstraint(_aufzaehlung("tageszaehlung", Tageszaehlung), name="tageszaehlung"),
        CheckConstraint(_aufzaehlung("zinsbeginn", Zinsbeginn), name="zinsbeginn"),
        CheckConstraint(_aufzaehlung("zahltag", Zahltag), name="zahltag"),
        CheckConstraint(_aufzaehlung("teilung", Teilung), name="teilung"),
        CheckConstraint(
            "(anrechnung = 'individuell') = (reihenfolge IS NOT NULL)",
            name="reihenfolge_individuell",
        ),
        CheckConstraint(
            "reihenfolge IS NULL OR (cardinality(reihenfolge) = 3"
            " AND reihenfolge @> ARRAY['kosten', 'zinsen', 'hauptforderung'])",
            name="reihenfolge_gruppen",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"), index=True)
    glaeubiger_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("glaeubiger.id"), index=True)
    aktenzeichen_glaeubiger: Mapped[str | None] = mapped_column(Text)
    # Bis zur Entscheidung über P-11 (Kap. 4.5).
    richtung: Mapped[str] = mapped_column(Text, server_default=sql_text("'verbindlichkeit'"))
    verbraucherdarlehen: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    anrechnung: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Anrechnungsregel.BGB_367.value}'")
    )
    # Nur bei anrechnung = individuell: die Gruppen in der vereinbarten Reihenfolge.
    reihenfolge: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    tageszaehlung: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Tageszaehlung.ACT_365.value}'")
    )
    zinsbeginn: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Zinsbeginn.GENANNTER_TAG.value}'")
    )
    zahltag: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Zahltag.ALTER_BETRAG.value}'")
    )
    teilung: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Teilung.KALENDER.value}'")
    )
    angelegt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AkteKonto(Basis):
    """Konten einer Akte (Kap. 4.2); die Buchungen einer Akte ergeben sich aus ihren Postings."""

    __tablename__ = "akte_konto"

    akte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("akte.id"), primary_key=True)
    konto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("konto.id"), primary_key=True, unique=True
    )


class AkteTeilungstag(Basis):
    """Erster Tag eines neuen Abschnitts, je Akte und Tag höchstens einmal (E-32)."""

    __tablename__ = "akte_teilungstag"

    akte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("akte.id"), primary_key=True)
    tag: Mapped[date] = mapped_column(Date, primary_key=True)


class BestandteilZeile(Basis):
    """Bestandteil einer Akte (Kap. 3, 4.5) mit seinem Passivkonto (Kap. 4.2)."""

    __tablename__ = "bestandteil"
    __table_args__ = (
        CheckConstraint(_aufzaehlung("art", Bestandteilart), name="art"),
        CheckConstraint("ursprungsbetrag > 0", name="ursprungsbetrag_positiv"),
        CheckConstraint("kennung <> ''", name="kennung_nicht_leer"),
        UniqueConstraint("akte_id", "kennung", name="uq_bestandteil_akte_id_kennung"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    akte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("akte.id"), index=True)
    kennung: Mapped[str] = mapped_column(Text)
    art: Mapped[str] = mapped_column(Text)
    konto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("konto.id"), unique=True)
    ursprungsbetrag: Mapped[Decimal] = mapped_column(BetragTyp())
    entstanden_am: Mapped[date | None] = mapped_column(Date)
    faellig_am: Mapped[date | None] = mapped_column(Date)
    kenntnis_am: Mapped[date | None] = mapped_column(Date)
    # Reihenfolge der Eingabe (E-35); vergibt die Datenbank (Migration 0004).
    laufnummer: Mapped[int] = mapped_column(BigInteger, Identity(always=True))


class ZinsregelZeile(Basis):
    """Zinsregel eines Bestandteils (Kap. 4.5, 5.2); verzinsliche mit eigenem Zinskonto."""

    __tablename__ = "zinsregel"
    __table_args__ = (
        CheckConstraint(_aufzaehlung("typ", Zinsregeltyp), name="typ"),
        CheckConstraint(werte_in("quelle", QUELLEN_ZINSREGEL), name="quelle"),
        CheckConstraint("(typ = 'keine') = (konto_id IS NULL)", name="konto_nur_verzinslich"),
        CheckConstraint("(typ = 'basiszins_plus') = (aufschlag IS NOT NULL)", name="aufschlag"),
        CheckConstraint("(typ = 'fest') = (satz IS NOT NULL)", name="satz"),
        CheckConstraint("typ = 'keine' OR ab IS NOT NULL", name="ab_verzinslich"),
        CheckConstraint("typ <> 'keine' OR bis IS NULL", name="bis_nicht_bei_keine"),
        CheckConstraint("bis IS NULL OR ab IS NULL OR bis >= ab", name="bis_nicht_vor_ab"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    bestandteil_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bestandteil.id"), index=True)
    typ: Mapped[str] = mapped_column(Text)
    # Prozentpunkte bzw. Prozent; NUMERIC ohne Skala rundet nie (kein Betrag).
    aufschlag: Mapped[Decimal | None] = mapped_column(Numeric())
    satz: Mapped[Decimal | None] = mapped_column(Numeric())
    ab: Mapped[date | None] = mapped_column(Date)
    bis: Mapped[date | None] = mapped_column(Date)
    quelle: Mapped[str | None] = mapped_column(Text)
    konto_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("konto.id"), unique=True)


class EreignisZeile(Basis):
    """Ereignis einer Akte (Kap. 4.5). Bei ``zahlung`` verweist es auf die Buchung.

    Ein Ereignis mit Buchung ändert und löscht die Datenbank nicht; eine falsch erfasste
    Zahlung wird storniert (Kap. 4.1, E-26).
    """

    __tablename__ = "ereignis"
    __table_args__ = (
        CheckConstraint("typ ~ '^[a-z_]+$'", name="typ_format"),
        CheckConstraint("(typ = 'zahlung') = (buchung_id IS NOT NULL)", name="buchung_bei_zahlung"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_objekt"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    akte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("akte.id"), index=True)
    typ: Mapped[str] = mapped_column(Text)
    datum: Mapped[date | None] = mapped_column(Date)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sql_text("'{}'::jsonb"))
    buchung_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buchung.id"), unique=True)
    erfasst_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
