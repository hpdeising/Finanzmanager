# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften des Statusmodells (Fachkonzept Kap. 6), mit zufälligen Fällen.

- Nach dem Ausgleich ist die Akte in der Nachwirkung oder geschlossen, sonst nie (E-37).
- Ohne Ausgleich gibt es keine Nachwirkungs-Aufgaben.
"""

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.berechnung import berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Ereignistyp,
    Zahlung,
)
from app.module.verbindlichkeiten.status import Status, status_berechnen

REIHE = lade_basiszinsreihe()
STICHTAG = date(2026, 12, 31)
HF = Bestandteil("hauptforderung", Bestandteilart.HAUPTFORDERUNG, Decimal("1000.00"))
TAGE = st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31))
BETRAEGE = st.integers(min_value=1, max_value=60000).map(lambda c: Decimal(c) / 100)
EREIGNISSE = st.lists(
    st.tuples(st.sampled_from(list(Ereignistyp)), TAGE).map(lambda t: Ereignis(t[0], t[1])),
    max_size=6,
)


@given(st.lists(st.tuples(TAGE, BETRAEGE), max_size=5), EREIGNISSE)
def test_nachwirkung_genau_bei_ausgleich(
    zahlungen: list[tuple[date, Decimal]], ereignisse: list[Ereignis]
) -> None:
    ergebnis = berechne(
        Aktenparameter(), [HF], [Zahlung(d, b) for d, b in zahlungen], STICHTAG, REIHE
    )
    status = status_berechnen(ereignisse, STICHTAG, ergebnis)
    ausgeglichen = ergebnis.gesamt == 0 and bool(zahlungen)
    assert (status.status in {Status.NACHWIRKUNG, Status.GESCHLOSSEN}) is ausgeglichen
    assert bool(status.aufgaben) is ausgeglichen
    assert status.status is not Status.AUSGEGLICHEN
