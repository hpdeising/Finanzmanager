# SPDX-License-Identifier: AGPL-3.0-or-later
"""``frontend/openapi.json`` entspricht der Anwendung (CLAUDE.md, Stack).

Die Oberfläche erzeugt ihre Typen aus dieser Datei, nie von Hand. Weicht sie ab, ist sie neu
zu erzeugen: ``uv run python -m app.api.openapi > ../frontend/openapi.json``.
"""

from pathlib import Path

from app.api.openapi import openapi_json

DATEI = Path(__file__).resolve().parents[3] / "frontend" / "openapi.json"


def test_openapi_json_ist_aktuell() -> None:
    assert DATEI.read_text(encoding="utf-8") == openapi_json(), (
        "frontend/openapi.json ist veraltet: uv run python -m app.api.openapi"
        " > ../frontend/openapi.json"
    )
