# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine und Sitzungen für die Anwendung.

Die Anwendung verbindet sich mit der Laufzeitrolle (Fachkonzept 11.1, E-19); die Adresse
steht in ``FINANZMANAGER_DATABASE_URL`` (Vorlage: ``.env.example``).
"""

import os
from typing import Final

from sqlalchemy import URL, Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker

URL_VARIABLE: Final = "FINANZMANAGER_DATABASE_URL"


def erzeuge_engine(url: str | URL | None = None) -> Engine:
    """Engine für PostgreSQL aus ``url`` oder ``FINANZMANAGER_DATABASE_URL``.

    - Nur PostgreSQL: Die Invarianten des Buchungskerns erzwingt die Datenbank selbst
      (Fachkonzept 4.4); eine andere Datenbank hätte sie nicht.
    - ``hide_parameters``: Gebundene Werte wie Beträge und Buchungstexte erscheinen nicht in
      Fehlermeldungen und damit nicht in Logs (CLAUDE.md, Sicherheit).
    - Zeitzone der Sitzung UTC: Zeitstempel kommen als ``datetime`` in UTC zurück, unabhängig
      von der Einstellung des Servers (CLAUDE.md, Datum und Fristen).
    """
    ziel = url if url is not None else os.environ.get(URL_VARIABLE)
    if not ziel:
        msg = f"Umgebungsvariable {URL_VARIABLE} ist nicht gesetzt."
        raise RuntimeError(msg)
    adresse = make_url(ziel)
    if adresse.get_backend_name() != "postgresql":
        msg = "Der Finanzmanager unterstützt nur PostgreSQL."
        raise ValueError(msg)
    return create_engine(
        adresse,
        hide_parameters=True,
        connect_args={"options": "-c TimeZone=UTC"},
    )


def sitzungsfabrik(engine: Engine) -> sessionmaker[Session]:
    """Sitzungen an ``engine``; Objekte bleiben nach dem Commit lesbar."""
    return sessionmaker(engine, expire_on_commit=False)
