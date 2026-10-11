# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine-Fabrik: nur PostgreSQL, keine Parameter in Fehlermeldungen, Zeitstempel in UTC."""

from datetime import timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine, sitzungsfabrik
from app.kern.db.engine import URL_VARIABLE


def test_fehlende_umgebungsvariable_wird_genannt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(URL_VARIABLE, raising=False)
    with pytest.raises(RuntimeError, match=URL_VARIABLE):
        erzeuge_engine()


def test_adresse_kommt_aus_der_umgebung(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(URL_VARIABLE, "postgresql+psycopg://finanzmanager_app@127.0.0.1/beispiel")
    engine = erzeuge_engine()
    assert engine.url.database == "beispiel"


@pytest.mark.parametrize("url", ["sqlite://", "mysql+pymysql://nutzer@127.0.0.1/db"])
def test_nur_postgresql(url: str) -> None:
    """Die Invarianten des Buchungskerns erzwingt nur PostgreSQL (Fachkonzept 4.4)."""
    with pytest.raises(ValueError, match="PostgreSQL"):
        erzeuge_engine(url)


def test_parameter_erscheinen_nicht_in_fehlermeldungen() -> None:
    """Beträge und Texte gehören nicht in Logs (CLAUDE.md, Sicherheit)."""
    engine = erzeuge_engine("postgresql+psycopg://finanzmanager_app@127.0.0.1/beispiel")
    assert engine.hide_parameters is True


def test_zeitzone_der_sitzung_ist_utc(app_engine: Engine) -> None:
    """Die Sitzungsdatenbank steht absichtlich auf Europe/Berlin; die Engine stellt UTC ein."""
    with app_engine.connect() as verbindung:
        assert verbindung.execute(text("SHOW TimeZone")).scalar_one() == "UTC"
        jetzt = verbindung.execute(text("SELECT now()")).scalar_one()
    assert jetzt.utcoffset() == timedelta(0)


def test_sitzungsfabrik_bindet_an_die_engine(app_engine: Engine) -> None:
    fabrik = sitzungsfabrik(app_engine)
    with fabrik() as sitzung:
        assert isinstance(sitzung, Session)
        assert sitzung.execute(text("SELECT current_user")).scalar_one() == "finanzmanager_app"
