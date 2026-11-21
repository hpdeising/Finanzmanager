# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAPI-Beschreibung als JSON, Quelle der Typen der Oberfläche (CLAUDE.md, Stack).

Aufruf aus ``backend/``::

    uv run python -m app.api.openapi > ../frontend/openapi.json

Ein Test prüft, dass ``frontend/openapi.json`` dem Stand der Anwendung entspricht.
"""

import json
import sys

from sqlalchemy.orm import sessionmaker

from app.api.app import erzeuge_app


def openapi_json() -> str:
    """Beschreibung der Anwendung, ohne Datenbank; Schlüssel sortiert, mit Zeilenende."""
    app = erzeuge_app(sitzungen=sessionmaker())
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(openapi_json())
