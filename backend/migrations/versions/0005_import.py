# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import von Zahlungen: CSV-Profile, Importläufe, Importzeilen und ihre Buchungen.

Revision: 0005
Vorgänger: 0004

Umsetzung von Fachkonzept Kap. 8 und 4.5 für Meilenstein M6, Teil Kern. Alle Tabellen sind
Kern-Tabellen und verweisen nur auf Kern-Tabellen (E-17); die Zuordnung zur Akte macht das
Modul.

- csv_profil: Profil je Bank und Haushalt (Kap. 8, Formate). Ein Name kommt je Haushalt
  einmal vor.
- import_lauf: eine hochgeladene Datei. Die Datei selbst wird nicht gespeichert (Kap. 8,
  Datenminimierung); gespeichert sind Format, Name des CSV-Profils, die Einstellung zu P-16
  und die Zahl der gelesenen Umsätze. Ist der Lauf abgeschlossen, nimmt er keine Buchung
  mehr an.
- import_zeile: ein Zahlungskandidat, also eine Belastung, die keine Rückbuchung ist
  (Kap. 8, Schritt 2). Gutschriften und Rückbuchungen werden nie gespeichert. ``datum`` ist
  die Wertstellung nach P-16, ``schluessel`` der Hash für Duplikate (Kap. 8, Schritt 3).
  Status ``offen`` oder ``gebucht``. Ein Schlüssel ist je Haushalt höchstens einmal gebucht;
  das erzwingt ein eindeutiger Teilindex.
- import_zeile_buchung: die Buchungen, die aus einer Zeile entstanden sind, je Akte eine
  (Kap. 4.5). Jede Buchung stammt aus höchstens einer Zeile.

Unveränderlichkeit: Eine gebuchte Zeile und ihre Verknüpfungen ändert und löscht die
Datenbank nicht. Offene Zeilen löscht der Abschluss des Laufs (Kap. 8, Datenminimierung).

Rechte der Laufzeitrolle (E-19): CSV-Profile sind Einstellungen und frei änderbar. Einen
Lauf darf sie anlegen und nur abschließen (``abgeschlossen_am``). Eine Zeile darf sie
anlegen, löschen und nur ihren Status ändern; Verknüpfungen nur anlegen.

Rückweg: Er bricht ab, sobald eine der vier Tabellen Zeilen hat (wie bei 0002 und 0004).
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | tuple[str, ...] | None = "0004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

FORMATE = ("csv", "camt053")
WERTSTELLUNG_AUS = ("buchungstag", "valuta")
STATUS = ("offen", "gebucht")

APP = "finanzmanager_app"
TABELLEN = ("import_zeile_buchung", "import_zeile", "import_lauf", "csv_profil")

ZEILE_FUNKTION = """
CREATE FUNCTION public.import_zeile_gebucht() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status = 'offen' AND NEW.status = 'gebucht'
            AND to_jsonb(NEW) - 'status' = to_jsonb(OLD) - 'status' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' AND OLD.status = 'offen' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION USING
        MESSAGE = 'Eine Importzeile wird nur von offen auf gebucht gesetzt; eine gebuchte'
            ' Zeile wird nicht geändert oder gelöscht (Fachkonzept 8).',
        ERRCODE = 'integrity_constraint_violation',
        CONSTRAINT = 'import_zeile_unveraenderlich';
END
$$
"""

ZEILE_TRIGGER = """
CREATE TRIGGER import_zeile_unveraenderlich
BEFORE UPDATE OR DELETE ON public.import_zeile
FOR EACH ROW EXECUTE FUNCTION public.import_zeile_gebucht()
"""

VERKNUEPFUNG_FUNKTION = """
CREATE FUNCTION public.import_zeile_buchung_unveraenderlich() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'Die Buchungen einer Importzeile werden nicht geändert oder gelöscht'
            ' (Fachkonzept 8).',
        ERRCODE = 'integrity_constraint_violation',
        CONSTRAINT = 'import_zeile_buchung_unveraenderlich';
END
$$
"""

VERKNUEPFUNG_TRIGGER = """
CREATE TRIGGER import_zeile_buchung_unveraenderlich
BEFORE UPDATE OR DELETE ON public.import_zeile_buchung
FOR EACH ROW EXECUTE FUNCTION public.import_zeile_buchung_unveraenderlich()
"""


def _in(spalte: str, werte: tuple[str, ...]) -> str:
    return f"{spalte} IN (" + ", ".join(f"'{wert}'" for wert in werte) + ")"


def _uuid_pk() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _zeitstempel(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _ein_zeichen(spalte: str) -> str:
    return f"char_length({spalte}) = 1"


def upgrade() -> None:
    op.create_table(
        "csv_profil",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("spalte_buchungstag", sa.Text(), nullable=False),
        sa.Column("spalte_betrag", sa.Text(), nullable=False),
        sa.Column("spalten_verwendungszweck", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("spalte_valuta", sa.Text(), nullable=True),
        sa.Column("spalte_gegen_name", sa.Text(), nullable=True),
        sa.Column("spalte_gegen_iban", sa.Text(), nullable=True),
        sa.Column("trennzeichen", sa.Text(), nullable=False),
        sa.Column("kodierung", sa.Text(), nullable=False),
        sa.Column("datumsformat", sa.Text(), nullable=False),
        sa.Column("dezimaltrennzeichen", sa.Text(), nullable=False),
        sa.Column("tausendertrennzeichen", sa.Text(), nullable=True),
        sa.Column("kopfzeilen_ueberspringen", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_csv_profil")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_csv_profil_haushalt_id_haushalt")
        ),
        sa.UniqueConstraint("haushalt_id", "name", name=op.f("uq_csv_profil_haushalt_id")),
        sa.CheckConstraint("name <> ''", name=op.f("ck_csv_profil_name_nicht_leer")),
        sa.CheckConstraint(
            "cardinality(spalten_verwendungszweck) >= 1",
            name=op.f("ck_csv_profil_verwendungszweck_vorhanden"),
        ),
        sa.CheckConstraint(_ein_zeichen("trennzeichen"), name=op.f("ck_csv_profil_trennzeichen")),
        sa.CheckConstraint(
            _ein_zeichen("dezimaltrennzeichen"), name=op.f("ck_csv_profil_dezimaltrennzeichen")
        ),
        sa.CheckConstraint(
            "tausendertrennzeichen IS NULL OR (" + _ein_zeichen("tausendertrennzeichen") + ""
            " AND tausendertrennzeichen <> dezimaltrennzeichen)",
            name=op.f("ck_csv_profil_tausendertrennzeichen"),
        ),
        sa.CheckConstraint(
            "kopfzeilen_ueberspringen >= 0", name=op.f("ck_csv_profil_kopfzeilen_nicht_negativ")
        ),
    )

    op.create_table(
        "import_lauf",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("profil_name", sa.Text(), nullable=True),
        sa.Column("wertstellung_aus", sa.Text(), nullable=False),
        sa.Column("umsaetze_gelesen", sa.Integer(), nullable=False),
        _zeitstempel("angelegt_am"),
        sa.Column("abgeschlossen_am", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_lauf")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_import_lauf_haushalt_id_haushalt")
        ),
        sa.UniqueConstraint("id", "haushalt_id", name=op.f("uq_import_lauf_id")),
        sa.CheckConstraint(_in("format", FORMATE), name=op.f("ck_import_lauf_format")),
        sa.CheckConstraint(
            _in("wertstellung_aus", WERTSTELLUNG_AUS), name=op.f("ck_import_lauf_wertstellung_aus")
        ),
        sa.CheckConstraint(
            "(format = 'csv') = (profil_name IS NOT NULL)",
            name=op.f("ck_import_lauf_profil_nur_bei_csv"),
        ),
        sa.CheckConstraint(
            "umsaetze_gelesen >= 0", name=op.f("ck_import_lauf_umsaetze_nicht_negativ")
        ),
    )
    op.create_index(op.f("ix_import_lauf_haushalt_id"), "import_lauf", ["haushalt_id"])

    op.create_table(
        "import_zeile",
        _uuid_pk(),
        sa.Column("lauf_id", sa.Uuid(), nullable=False),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("buchungstag", sa.Date(), nullable=False),
        sa.Column("valuta", sa.Date(), nullable=True),
        sa.Column("betrag", sa.Numeric(19, 4), nullable=False),
        sa.Column("gegen_name", sa.Text(), nullable=True),
        sa.Column("gegen_iban", sa.Text(), nullable=True),
        sa.Column("verwendungszweck", sa.Text(), nullable=False),
        sa.Column("schluessel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'offen'"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_zeile")),
        sa.ForeignKeyConstraint(
            ["lauf_id", "haushalt_id"],
            ["import_lauf.id", "import_lauf.haushalt_id"],
            name=op.f("fk_import_zeile_lauf_id_import_lauf"),
        ),
        sa.UniqueConstraint("lauf_id", "position", name=op.f("uq_import_zeile_lauf_id")),
        sa.CheckConstraint("betrag > 0", name=op.f("ck_import_zeile_betrag_positiv")),
        sa.CheckConstraint("position >= 1", name=op.f("ck_import_zeile_position_positiv")),
        sa.CheckConstraint(
            "schluessel ~ '^[0-9a-f]{64}$'", name=op.f("ck_import_zeile_schluessel_format")
        ),
        sa.CheckConstraint(_in("status", STATUS), name=op.f("ck_import_zeile_status")),
    )
    op.create_index(
        "uq_import_zeile_gebucht_schluessel",
        "import_zeile",
        ["haushalt_id", "schluessel"],
        unique=True,
        postgresql_where=sa.text("status = 'gebucht'"),
    )

    op.create_table(
        "import_zeile_buchung",
        sa.Column("zeile_id", sa.Uuid(), nullable=False),
        sa.Column("buchung_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("zeile_id", "buchung_id", name=op.f("pk_import_zeile_buchung")),
        sa.ForeignKeyConstraint(
            ["zeile_id"],
            ["import_zeile.id"],
            name=op.f("fk_import_zeile_buchung_zeile_id_import_zeile"),
        ),
        sa.ForeignKeyConstraint(
            ["buchung_id"], ["buchung.id"], name=op.f("fk_import_zeile_buchung_buchung_id_buchung")
        ),
        sa.UniqueConstraint("buchung_id", name=op.f("uq_import_zeile_buchung_buchung_id")),
    )

    op.execute(ZEILE_FUNKTION)
    op.execute(ZEILE_TRIGGER)
    op.execute(VERKNUEPFUNG_FUNKTION)
    op.execute(VERKNUEPFUNG_TRIGGER)

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.csv_profil TO {APP}")
    op.execute(f"GRANT SELECT, INSERT ON public.import_lauf TO {APP}")
    op.execute(f"GRANT UPDATE (abgeschlossen_am) ON public.import_lauf TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON public.import_zeile TO {APP}")
    op.execute(f"GRANT UPDATE (status) ON public.import_zeile TO {APP}")
    op.execute(f"GRANT SELECT, INSERT ON public.import_zeile_buchung TO {APP}")


def downgrade() -> None:
    for tabelle in TABELLEN:
        op.execute(f"LOCK TABLE public.{tabelle} IN ACCESS EXCLUSIVE MODE")
    # Die Tabellennamen sind Konstanten dieser Datei, keine Eingaben.
    vorhanden = " OR ".join(
        f"EXISTS (SELECT 1 FROM public.{tabelle})"  # noqa: S608
        for tabelle in TABELLEN
    )
    op.execute(
        "DO $$ BEGIN"
        f" IF {vorhanden} THEN"
        " RAISE EXCEPTION USING"
        " MESSAGE = 'Rückweg von 0005 würde CSV-Profile oder Importe löschen; abgebrochen.',"
        " ERRCODE = 'object_not_in_prerequisite_state';"
        " END IF;"
        " END $$"
    )
    op.execute("DROP TRIGGER import_zeile_buchung_unveraenderlich ON public.import_zeile_buchung")
    op.execute("DROP FUNCTION public.import_zeile_buchung_unveraenderlich()")
    op.execute("DROP TRIGGER import_zeile_unveraenderlich ON public.import_zeile")
    op.execute("DROP FUNCTION public.import_zeile_gebucht()")
    for tabelle in TABELLEN:
        op.drop_table(tabelle)
