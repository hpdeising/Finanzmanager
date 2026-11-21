# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laufnummer der Bestandteile.

Revision: 0004
Vorgänger: 0003

Umsetzung von E-35 mit der Entscheidung vom 21.11.2026: „Reihenfolge der Eingabe“ ist die
aufsteigende Laufnummer eines Bestandteils. Sie ist eine Identity-Spalte (GENERATED ALWAYS)
und kein Zeitstempel, weil mehrere Bestandteile in einer Transaktion dasselbe now() hätten.
Die Datenbank vergibt sie; die Laufzeitrolle kann sie weder vorgeben noch ändern. Bestehende
Bestandteile bekommen beim Anlegen der Spalte Nummern in der Reihenfolge, in der PostgreSQL
die Zeilen liest; vor 0004 gab es keine verlässliche Reihenfolge der Eingabe.

Rückweg: Er bricht ab, wenn es Bestandteile gibt, weil ihre Reihenfolge verloren ginge (wie
bei 0002).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | tuple[str, ...] | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "bestandteil",
        sa.Column("laufnummer", sa.BigInteger(), sa.Identity(always=True), nullable=False),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE public.bestandteil IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ BEGIN"
        " IF EXISTS (SELECT 1 FROM public.bestandteil) THEN"
        " RAISE EXCEPTION USING"
        " MESSAGE = 'Rückweg von 0004 würde die Reihenfolge der Eingabe verlieren;"
        " abgebrochen.',"
        " ERRCODE = 'object_not_in_prerequisite_state';"
        " END IF;"
        " END $$"
    )
    op.drop_column("bestandteil", "laufnummer")
