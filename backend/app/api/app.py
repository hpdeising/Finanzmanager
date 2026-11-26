# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI-Anwendung: registriert die Routen von Kern und Modulen.

Start (nur an 127.0.0.1, Fachkonzept 11.1)::

    uvicorn app.api:erzeuge_app --factory --host 127.0.0.1 --port 8000

Die Datenbank kommt aus ``FINANZMANAGER_DATABASE_URL`` (Laufzeitrolle, ``.env.example``).
"""

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.kern.db import erzeuge_engine, sitzungsfabrik
from app.kern.stammdaten import lade_basiszinsreihe, lade_feiertagskalender
from app.kern.web import Stammdaten, import_router
from app.kern.web import router as kern_router
from app.kern.web.router import laufende_version
from app.module.verbindlichkeiten.api import router as verbindlichkeiten_router


def erzeuge_app(sitzungen: sessionmaker[Session] | None = None) -> FastAPI:
    """Anwendung mit Sitzungsfabrik; ohne Angabe aus ``FINANZMANAGER_DATABASE_URL``.

    Die Stammdaten werden beim Start geladen und geprüft; eine kaputte Datei verhindert den
    Start (Fachkonzept Kap. 7).
    """
    app = FastAPI(title="Finanzmanager", version=laufende_version())
    app.state.sitzungen = sitzungen or sitzungsfabrik(erzeuge_engine())
    app.state.stammdaten = Stammdaten(
        basiszinsreihe=lade_basiszinsreihe(), feiertage=lade_feiertagskalender()
    )
    app.include_router(kern_router)
    app.include_router(import_router)
    app.include_router(verbindlichkeiten_router)
    return app
