# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine und Sitzungen für die Anwendung.

Die Anwendung verbindet sich mit der Laufzeitrolle (Fachkonzept 11.1, E-19); die Adresse
steht in ``FINANZMANAGER_DATABASE_URL`` (Vorlage: ``.env.example``).
"""

import os
from typing import Final

from sqlalchemy import URL, Engine, create_engine, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

URL_VARIABLE: Final = "FINANZMANAGER_DATABASE_URL"


def lies_adresse(wert: str | URL, *, quelle: str = "Datenbank") -> URL:
    """SQLAlchemy-Adresse lesen, ohne dass eine Meldung Teile des Passworts zitiert.

    Bei einer kaputten Adresse, etwa einem nicht kodierten ``@`` im Passwort, nennt
    SQLAlchemy den Rest der Adresse samt Passwort in der Meldung.
    """
    if isinstance(wert, URL):
        return wert
    try:
        return make_url(wert)
    except (ArgumentError, ValueError):
        msg = (
            f"Ungültige Adresse ({quelle}). Sonderzeichen im Passwort prozentkodieren,"
            " z. B. @ als %40."
        )
        raise ValueError(msg) from None


def erzeuge_engine(url: str | URL | None = None) -> Engine:
    """Engine für PostgreSQL aus ``url`` oder ``FINANZMANAGER_DATABASE_URL``.

    - Nur PostgreSQL: Die Invarianten des Buchungskerns erzwingt die Datenbank selbst
      (Fachkonzept 4.4); eine andere Datenbank hätte sie nicht.
    - ``hide_parameters``: SQLAlchemy nennt gebundene Werte wie Beträge und Buchungstexte
      nicht in seinen Fehlermeldungen. Das DETAIL von PostgreSQL kann bei CHECK- und
      NOT-NULL-Verletzungen trotzdem die ganze Zeile enthalten; Logs schreiben deshalb nur
      SQLSTATE und Regelname (CLAUDE.md, Sicherheit).
    - Zeitzone der Sitzung UTC: Zeitstempel kommen als ``datetime`` in UTC zurück, unabhängig
      von der Einstellung des Servers (CLAUDE.md, Datum und Fristen). Gesetzt wird sie nach
      dem Verbindungsaufbau, damit weder ``options`` noch ``PGOPTIONS`` oder ``PGTZ`` sie
      überschreiben. Andere Sitzungsparameter aus ``options`` in der Adresse oder, ohne sie,
      aus ``PGOPTIONS`` wirken wie bei libpq üblich.
    """
    ziel = url if url is not None else os.environ.get(URL_VARIABLE)
    if not ziel:
        msg = f"Umgebungsvariable {URL_VARIABLE} ist nicht gesetzt."
        raise RuntimeError(msg)
    adresse = lies_adresse(ziel, quelle=URL_VARIABLE if url is None else "Datenbank")
    if adresse.get_backend_name() != "postgresql":
        msg = "Der Finanzmanager unterstützt nur PostgreSQL."
        raise ValueError(msg)
    engine = create_engine(adresse, hide_parameters=True)
    event.listen(engine, "connect", _setze_utc)
    return engine


def _setze_utc(verbindung: DBAPIConnection, _eintrag: ConnectionPoolEntry) -> None:
    """Zeitzone UTC für jede neue Verbindung; committet, damit kein Rollback sie zurücknimmt."""
    cursor = verbindung.cursor()
    try:
        cursor.execute("SET TIME ZONE 'UTC'")
    finally:
        cursor.close()
    verbindung.commit()


def sitzungsfabrik(engine: Engine) -> sessionmaker[Session]:
    """Sitzungen an ``engine``; Objekte bleiben nach dem Commit lesbar."""
    return sessionmaker(engine, expire_on_commit=False)
