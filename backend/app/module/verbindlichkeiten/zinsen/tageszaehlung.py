# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zinstage und Tagesbasis eines Abschnitts (Fachkonzept Kap. 5.1, E-22, E-31, E-34).

Keine Rechtsregel: Eine verbindliche Quelle für die Zählung gibt es nicht (E-34). Die Arten
sind Festlegungen des Fachkonzepts, je Akte wählbar.
"""

import calendar
from datetime import date, timedelta

from app.module.verbindlichkeiten.domain import Tageszaehlung

_TAGESBASIS = {
    Tageszaehlung.ACT_365: 365,
    Tageszaehlung.ACT_360: 360,
    Tageszaehlung.DREISSIG_360: 360,
}


def zinstage(von: date, bis: date, zaehlung: Tageszaehlung, vortag_verzinst: bool) -> int:
    """Zinstage des Abschnitts vom ersten Tag ``von`` bis zum letzten Tag ``bis``.

    Taggenaue Arten (``act_365``, ``act_act``, ``act_360``) zählen jeden Kalendertag, den ersten
    wie den letzten (Kap. 5.1). Bei ``act_act`` darf der Abschnitt keinen Jahreswechsel
    enthalten, weil an jedem 01.01. geteilt wird (E-31).

    ``30_360`` (E-34): 360·(J2-J1) + 30·(M2-M1) + (T2-T1) mit D1 = Vortag des ersten Tags und
    D2 = letzter Tag. Ist der Vortag kein verzinster Tag desselben Bestandteils
    (``vortag_verzinst`` falsch: erster Zinstag oder nach einer Pause), ist D1 der erste Tag
    selbst, und es kommt + 1 dazu. Ein Tag 31 zählt bei D1 und D2 als 30.

    Raises:
        ValueError: wenn ``bis`` vor ``von`` liegt oder ein ``act_act``-Abschnitt über einen
            Jahreswechsel reicht.
    """
    if bis < von:
        msg = "Ende des Abschnitts liegt vor seinem Beginn."
        raise ValueError(msg)
    if zaehlung is Tageszaehlung.ACT_ACT and von.year != bis.year:
        msg = "Ein Abschnitt bei act_act darf keinen Jahreswechsel enthalten (E-31)."
        raise ValueError(msg)
    if zaehlung is not Tageszaehlung.DREISSIG_360:
        return (bis - von).days + 1
    if vortag_verzinst:
        return _dreissig_360(von - timedelta(days=1), bis)
    return _dreissig_360(von, bis) + 1


def tagesbasis(zaehlung: Tageszaehlung, von: date) -> int:
    """Tagesbasis eines Abschnitts mit erstem Tag ``von``.

    ``act_365``: immer 365, auch im Schaltjahr (E-22). ``act_act``: 366 in einem Schaltjahr,
    sonst 365 (E-31). ``act_360`` und ``30_360``: 360.
    """
    if zaehlung is Tageszaehlung.ACT_ACT:
        return 366 if calendar.isleap(von.year) else 365
    return _TAGESBASIS[zaehlung]


def _dreissig_360(d1: date, d2: date) -> int:
    t1 = min(d1.day, 30)
    t2 = min(d2.day, 30)
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (t2 - t1)
