# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zeitzone der Installation für fachliche Daten (CLAUDE.md, Datum und Fristen).

Zeitstempel speichert die Datenbank in UTC. Wird daraus ein fachlicher Tag, etwa „heute“ oder
der Tag, an dem eine Akte eröffnet wurde, gilt die Zeitzone der Installation.
"""

from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

ZEITZONE: Final = ZoneInfo("Europe/Berlin")


def heute() -> date:
    """Heutiger Tag in der Zeitzone der Installation."""
    return datetime.now(ZEITZONE).date()


def tag_von(zeitpunkt: datetime) -> date:
    """Kalendertag eines Zeitstempels in der Zeitzone der Installation.

    Raises:
        ValueError: bei einem Zeitstempel ohne Zeitzone.
    """
    if zeitpunkt.tzinfo is None:
        msg = "Zeitstempel ohne Zeitzone."
        raise ValueError(msg)
    return zeitpunkt.astimezone(ZEITZONE).date()
