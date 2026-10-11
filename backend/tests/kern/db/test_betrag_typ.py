# SPDX-License-Identifier: AGPL-3.0-or-later
"""BetragTyp: NUMERIC(19,4), das nie still rundet (CLAUDE.md, Geld; Fachkonzept 4.4)."""

from decimal import Decimal

import pytest
from sqlalchemy import Column, MetaData, Numeric, Table, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError

from app.kern.db import Basis, BetragNichtSpeicherbarError, BetragTyp

DIALEKT = postgresql.dialect()
TABELLE = Table("beispiel", MetaData(), Column("betrag", BetragTyp()))


@pytest.mark.parametrize("wert", [Decimal("1.0001"), Decimal("-999999999999999.9999"), Decimal(0)])
def test_gebundene_werte_bleiben_unveraendert(wert: Decimal) -> None:
    assert BetragTyp().process_bind_param(wert, DIALEKT) == wert


def test_none_bleibt_none() -> None:
    assert BetragTyp().process_bind_param(None, DIALEKT) is None


@pytest.mark.parametrize("wert", [Decimal("1.00005"), Decimal("1E15"), 1.5])
def test_nicht_speicherbare_werte_werden_abgelehnt(wert: object) -> None:
    with pytest.raises(BetragNichtSpeicherbarError, match="Betrag"):
        BetragTyp().process_bind_param(wert, DIALEKT)  # pyright: ignore[reportArgumentType]


def test_ablehnung_ist_ein_value_error() -> None:
    assert issubclass(BetragNichtSpeicherbarError, ValueError)


def test_auch_der_literalpfad_lehnt_ab() -> None:
    """Auch SQL mit eingesetzten Literalen (z. B. Offline-Migrationen) rundet nicht still.

    Beim Übersetzen verpackt SQLAlchemy den Fehler in einen CompileError.
    """
    anweisung = insert(TABELLE).values(betrag=Decimal("1.00005"))
    with pytest.raises(CompileError) as fehler:
        anweisung.compile(dialect=DIALEKT, compile_kwargs={"literal_binds": True})
    assert isinstance(fehler.value.__cause__, BetragNichtSpeicherbarError)


def test_vergleichswerte_laufen_ebenfalls_durch_die_pruefung() -> None:
    abfrage = select(TABELLE).where(TABELLE.c.betrag == Decimal("0.00001"))
    with pytest.raises(CompileError) as fehler:
        abfrage.compile(dialect=DIALEKT, compile_kwargs={"literal_binds": True})
    assert isinstance(fehler.value.__cause__, BetragNichtSpeicherbarError)


def test_spaltentyp_ist_numeric_19_4() -> None:
    impl = BetragTyp().impl_instance
    assert isinstance(impl, Numeric)
    assert (impl.precision, impl.scale, impl.asdecimal) == (19, 4, True)


def test_namenskonvention_legt_alle_constraint_namen_fest() -> None:
    """Feste Namen, damit Migration, Modelle und Fehlermeldungen übereinstimmen."""
    konvention = dict(Basis.metadata.naming_convention)
    assert {"pk", "fk", "uq", "ck", "ix"} <= set(konvention)
