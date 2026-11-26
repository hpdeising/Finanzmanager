# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabellen des Imports (Fachkonzept Kap. 8, 4.5; Migration 0005).

Kern-Tabellen; sie verweisen nur auf Kern-Tabellen (E-17). Eine Importzeile ist ein
Zahlungskandidat, noch keine Zahlung. Die Buchungen, die aus ihr entstehen, legt ein Modul an
(je Akte eine) und verknüpft sie über ``markiere_gebucht()``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.kern.db import Basis, BetragTyp
from app.kern.import_.umsatz import WertstellungAus


class Format(StrEnum):
    CSV = "csv"
    CAMT053 = "camt053"


class Zeilenstatus(StrEnum):
    OFFEN = "offen"
    GEBUCHT = "gebucht"


def _werte_in(spalte: str, aufzaehlung: type[StrEnum]) -> str:
    return f"{spalte} IN (" + ", ".join(f"'{wert.value}'" for wert in aufzaehlung) + ")"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


def _ein_zeichen(spalte: str) -> str:
    return f"char_length({spalte}) = 1"


class CsvProfilZeile(Basis):
    """Gespeichertes CSV-Profil eines Haushalts (Kap. 8, Formate); ``als_profil()`` liest es."""

    __tablename__ = "csv_profil"
    __table_args__ = (
        UniqueConstraint("haushalt_id", "name"),
        CheckConstraint("name <> ''", name="name_nicht_leer"),
        CheckConstraint(
            "cardinality(spalten_verwendungszweck) >= 1", name="verwendungszweck_vorhanden"
        ),
        CheckConstraint(_ein_zeichen("trennzeichen"), name="trennzeichen"),
        CheckConstraint(_ein_zeichen("dezimaltrennzeichen"), name="dezimaltrennzeichen"),
        CheckConstraint(
            "tausendertrennzeichen IS NULL OR (" + _ein_zeichen("tausendertrennzeichen") + ""
            " AND tausendertrennzeichen <> dezimaltrennzeichen)",
            name="tausendertrennzeichen",
        ),
        CheckConstraint("kopfzeilen_ueberspringen >= 0", name="kopfzeilen_nicht_negativ"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"))
    name: Mapped[str] = mapped_column(Text)
    spalte_buchungstag: Mapped[str] = mapped_column(Text)
    spalte_betrag: Mapped[str] = mapped_column(Text)
    spalten_verwendungszweck: Mapped[list[str]] = mapped_column(ARRAY(Text))
    spalte_valuta: Mapped[str | None] = mapped_column(Text)
    spalte_gegen_name: Mapped[str | None] = mapped_column(Text)
    spalte_gegen_iban: Mapped[str | None] = mapped_column(Text)
    trennzeichen: Mapped[str] = mapped_column(Text)
    kodierung: Mapped[str] = mapped_column(Text)
    datumsformat: Mapped[str] = mapped_column(Text)
    dezimaltrennzeichen: Mapped[str] = mapped_column(Text)
    tausendertrennzeichen: Mapped[str | None] = mapped_column(Text)
    kopfzeilen_ueberspringen: Mapped[int] = mapped_column(Integer)


class ImportLauf(Basis):
    """Eine hochgeladene Datei; die Datei selbst wird nicht gespeichert (Kap. 8)."""

    __tablename__ = "import_lauf"
    __table_args__ = (
        UniqueConstraint("id", "haushalt_id"),
        CheckConstraint(_werte_in("format", Format), name="format"),
        CheckConstraint(_werte_in("wertstellung_aus", WertstellungAus), name="wertstellung_aus"),
        CheckConstraint("(format = 'csv') = (profil_name IS NOT NULL)", name="profil_nur_bei_csv"),
        CheckConstraint("umsaetze_gelesen >= 0", name="umsaetze_nicht_negativ"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"), index=True)
    format: Mapped[str] = mapped_column(Text)
    # Name des CSV-Profils beim Import; kein Verweis, damit ein Profil löschbar bleibt.
    profil_name: Mapped[str | None] = mapped_column(Text)
    # Einstellung zu P-16 für diesen Lauf.
    wertstellung_aus: Mapped[str] = mapped_column(Text)
    # Alle Umsätze der Datei, auch Gutschriften und Rückbuchungen, die nicht gespeichert sind.
    umsaetze_gelesen: Mapped[int] = mapped_column(Integer)
    angelegt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


GEBUCHT_EINDEUTIG: Final = "uq_import_zeile_gebucht_schluessel"


class ImportZeile(Basis):
    """Zahlungskandidat eines Laufs (Kap. 8, Schritt 2); immer eine Belastung, Betrag positiv.

    ``datum`` ist die Wertstellung nach P-16. ``schluessel`` ist der Hash für Duplikate
    (Kap. 8, Schritt 3); gebucht ist er je Haushalt höchstens einmal.
    """

    __tablename__ = "import_zeile"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lauf_id", "haushalt_id"], ["import_lauf.id", "import_lauf.haushalt_id"]
        ),
        UniqueConstraint("lauf_id", "position"),
        CheckConstraint("betrag > 0", name="betrag_positiv"),
        CheckConstraint("position >= 1", name="position_positiv"),
        CheckConstraint("schluessel ~ '^[0-9a-f]{64}$'", name="schluessel_format"),
        CheckConstraint(_werte_in("status", Zeilenstatus), name="status"),
        Index(
            GEBUCHT_EINDEUTIG,
            "haushalt_id",
            "schluessel",
            unique=True,
            postgresql_where=sql_text("status = 'gebucht'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lauf_id: Mapped[uuid.UUID] = mapped_column()
    haushalt_id: Mapped[uuid.UUID] = mapped_column()
    # Reihenfolge in der Datei, ab 1; nur Kandidaten werden gezählt.
    position: Mapped[int] = mapped_column(Integer)
    datum: Mapped[date] = mapped_column(Date)
    buchungstag: Mapped[date] = mapped_column(Date)
    valuta: Mapped[date | None] = mapped_column(Date)
    betrag: Mapped[Decimal] = mapped_column(BetragTyp())
    gegen_name: Mapped[str | None] = mapped_column(Text)
    gegen_iban: Mapped[str | None] = mapped_column(Text)
    verwendungszweck: Mapped[str] = mapped_column(Text)
    schluessel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, server_default=sql_text(f"'{Zeilenstatus.OFFEN.value}'")
    )


class ImportZeileBuchung(Basis):
    """Buchung, die aus einer Importzeile entstanden ist (je Akte eine, Kap. 4.5)."""

    __tablename__ = "import_zeile_buchung"

    zeile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_zeile.id"), primary_key=True)
    buchung_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buchung.id"), primary_key=True, unique=True
    )
