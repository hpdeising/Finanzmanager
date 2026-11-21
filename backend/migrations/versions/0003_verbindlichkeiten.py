# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabellen des Moduls Verbindlichkeiten und Bundesland des Haushalts.

Revision: 0003
Vorgänger: 0002

Umsetzung von Fachkonzept 4.2, 4.3 und 4.5 für Meilenstein M5:

- haushalt.bundesland: Land für die Feiertage, wenn bei einem Ereignis kein Gericht erfasst
  ist (Kap. 5.4). Optional; bestehende Haushalte haben noch keins.
- glaeubiger, akte, akte_konto, akte_teilungstag, bestandteil, zinsregel, ereignis. Die Tabellen
  verweisen auf Kern-Tabellen, nie umgekehrt (E-17).
- Eine Zahlung ist eine Buchung im Ledger und ein Ereignis zahlung mit Verweis auf sie
  (Kap. 4.3, 4.5). Ein Ereignis mit Buchung ändert und löscht die Datenbank nicht; eine
  falsch erfasste Zahlung wird storniert (Kap. 4.1).
- Der Status einer Akte wird berechnet und hat keine Spalte (E-38).

Rechte der Laufzeitrolle (E-19): Ereignisse, Zinsregeln, Teilungstage und Gläubiger darf
sie ändern, weil sich die Berechnung bei geänderten Eingaben ändern soll (Kap. 5.2
Schritt 7). Akten darf sie ändern, aber nicht löschen (Löschkonzept: P-10). Bestandteile
und die Konten einer Akte hängen am Ledger; dort darf sie nur Fälligkeit, Kenntnis und
Entstehung eines Bestandteils ändern, nicht Betrag, Art oder Konto.

Die Werte der Aufzählungen stehen hier wörtlich; die Modelle bilden sie aus den Aufzählungen
der Domain, ein Test vergleicht beide.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | tuple[str, ...] | None = "0002"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

LAENDER = (
    "BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH",
)  # fmt: skip
RICHTUNGEN = ("verbindlichkeit", "forderung")
ANRECHNUNG = ("bgb_367", "bgb_497", "individuell")
TAGESZAEHLUNG = ("act_365", "act_act", "act_360", "30_360")
ZINSBEGINN = ("genannter_tag", "folgetag")
ZAHLTAG = ("alter_betrag", "verminderter_betrag")
TEILUNG = ("kalender", "satzwechsel")
BESTANDTEILART = (
    "hauptforderung",
    "zinsen",
    "kosten_vorgerichtlich",
    "kosten_verfahren",
    "kosten_vollstreckung",
)
ZINSREGELTYP = (
    "gesetzlich_288_1",
    "gesetzlich_288_2",
    "kostenfestsetzung",
    "basiszins_plus",
    "fest",
    "keine",
)
QUELLEN_ZINSREGEL = ("titel", "vertrag")

APP = "finanzmanager_app"

EREIGNIS_FUNKTION = """
CREATE FUNCTION public.verbindlichkeiten_ereignis_mit_buchung() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'Ein Ereignis mit Buchung wird nicht geändert oder gelöscht, sondern storniert'
            ' (Fachkonzept 4.1).',
        ERRCODE = 'integrity_constraint_violation',
        CONSTRAINT = 'ereignis_mit_buchung_unveraenderlich';
END
$$
"""

EREIGNIS_TRIGGER = """
CREATE TRIGGER ereignis_mit_buchung_unveraenderlich
BEFORE UPDATE OR DELETE ON public.ereignis
FOR EACH ROW WHEN (OLD.buchung_id IS NOT NULL)
EXECUTE FUNCTION public.verbindlichkeiten_ereignis_mit_buchung()
"""


def _in(spalte: str, werte: tuple[str, ...]) -> str:
    return f"{spalte} IN (" + ", ".join(f"'{wert}'" for wert in werte) + ")"


def _uuid_pk() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _zeitstempel(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column("haushalt", sa.Column("bundesland", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_haushalt_bundesland"), "haushalt", _in("bundesland", LAENDER)
    )

    op.create_table(
        "glaeubiger",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("anschrift", sa.Text(), nullable=True),
        sa.Column("iban", sa.Text(), nullable=True),
        sa.Column("vertreter", sa.Text(), nullable=True),
        sa.Column("kontakt", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_glaeubiger")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_glaeubiger_haushalt_id_haushalt")
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_glaeubiger_name_nicht_leer")),
    )
    op.create_index(op.f("ix_glaeubiger_haushalt_id"), "glaeubiger", ["haushalt_id"])

    op.create_table(
        "akte",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("glaeubiger_id", sa.Uuid(), nullable=False),
        sa.Column("aktenzeichen_glaeubiger", sa.Text(), nullable=True),
        sa.Column(
            "richtung", sa.Text(), server_default=sa.text("'verbindlichkeit'"), nullable=False
        ),
        sa.Column(
            "verbraucherdarlehen", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("anrechnung", sa.Text(), server_default=sa.text("'bgb_367'"), nullable=False),
        sa.Column("reihenfolge", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("tageszaehlung", sa.Text(), server_default=sa.text("'act_365'"), nullable=False),
        sa.Column(
            "zinsbeginn", sa.Text(), server_default=sa.text("'genannter_tag'"), nullable=False
        ),
        sa.Column("zahltag", sa.Text(), server_default=sa.text("'alter_betrag'"), nullable=False),
        sa.Column("teilung", sa.Text(), server_default=sa.text("'kalender'"), nullable=False),
        _zeitstempel("angelegt_am"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_akte")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_akte_haushalt_id_haushalt")
        ),
        sa.ForeignKeyConstraint(
            ["glaeubiger_id"], ["glaeubiger.id"], name=op.f("fk_akte_glaeubiger_id_glaeubiger")
        ),
        sa.CheckConstraint(_in("richtung", RICHTUNGEN), name=op.f("ck_akte_richtung")),
        sa.CheckConstraint(_in("anrechnung", ANRECHNUNG), name=op.f("ck_akte_anrechnung")),
        sa.CheckConstraint(_in("tageszaehlung", TAGESZAEHLUNG), name=op.f("ck_akte_tageszaehlung")),
        sa.CheckConstraint(_in("zinsbeginn", ZINSBEGINN), name=op.f("ck_akte_zinsbeginn")),
        sa.CheckConstraint(_in("zahltag", ZAHLTAG), name=op.f("ck_akte_zahltag")),
        sa.CheckConstraint(_in("teilung", TEILUNG), name=op.f("ck_akte_teilung")),
        sa.CheckConstraint(
            "(anrechnung = 'individuell') = (reihenfolge IS NOT NULL)",
            name=op.f("ck_akte_reihenfolge_individuell"),
        ),
        sa.CheckConstraint(
            "reihenfolge IS NULL OR (cardinality(reihenfolge) = 3"
            " AND reihenfolge @> ARRAY['kosten', 'zinsen', 'hauptforderung'])",
            name=op.f("ck_akte_reihenfolge_gruppen"),
        ),
    )
    op.create_index(op.f("ix_akte_haushalt_id"), "akte", ["haushalt_id"])
    op.create_index(op.f("ix_akte_glaeubiger_id"), "akte", ["glaeubiger_id"])

    op.create_table(
        "akte_konto",
        sa.Column("akte_id", sa.Uuid(), nullable=False),
        sa.Column("konto_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("akte_id", "konto_id", name=op.f("pk_akte_konto")),
        sa.ForeignKeyConstraint(["akte_id"], ["akte.id"], name=op.f("fk_akte_konto_akte_id_akte")),
        sa.ForeignKeyConstraint(
            ["konto_id"], ["konto.id"], name=op.f("fk_akte_konto_konto_id_konto")
        ),
        sa.UniqueConstraint("konto_id", name=op.f("uq_akte_konto_konto_id")),
    )

    op.create_table(
        "akte_teilungstag",
        sa.Column("akte_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("akte_id", "tag", name=op.f("pk_akte_teilungstag")),
        sa.ForeignKeyConstraint(
            ["akte_id"], ["akte.id"], name=op.f("fk_akte_teilungstag_akte_id_akte")
        ),
    )

    op.create_table(
        "bestandteil",
        _uuid_pk(),
        sa.Column("akte_id", sa.Uuid(), nullable=False),
        sa.Column("kennung", sa.Text(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("konto_id", sa.Uuid(), nullable=False),
        sa.Column("ursprungsbetrag", sa.Numeric(19, 4), nullable=False),
        sa.Column("entstanden_am", sa.Date(), nullable=True),
        sa.Column("faellig_am", sa.Date(), nullable=True),
        sa.Column("kenntnis_am", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bestandteil")),
        sa.ForeignKeyConstraint(["akte_id"], ["akte.id"], name=op.f("fk_bestandteil_akte_id_akte")),
        sa.ForeignKeyConstraint(
            ["konto_id"], ["konto.id"], name=op.f("fk_bestandteil_konto_id_konto")
        ),
        sa.UniqueConstraint("konto_id", name=op.f("uq_bestandteil_konto_id")),
        sa.UniqueConstraint("akte_id", "kennung", name="uq_bestandteil_akte_id_kennung"),
        sa.CheckConstraint(_in("art", BESTANDTEILART), name=op.f("ck_bestandteil_art")),
        sa.CheckConstraint(
            "ursprungsbetrag > 0", name=op.f("ck_bestandteil_ursprungsbetrag_positiv")
        ),
        sa.CheckConstraint("kennung <> ''", name=op.f("ck_bestandteil_kennung_nicht_leer")),
    )
    op.create_index(op.f("ix_bestandteil_akte_id"), "bestandteil", ["akte_id"])

    op.create_table(
        "zinsregel",
        _uuid_pk(),
        sa.Column("bestandteil_id", sa.Uuid(), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("aufschlag", sa.Numeric(), nullable=True),
        sa.Column("satz", sa.Numeric(), nullable=True),
        sa.Column("ab", sa.Date(), nullable=True),
        sa.Column("bis", sa.Date(), nullable=True),
        sa.Column("quelle", sa.Text(), nullable=True),
        sa.Column("konto_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zinsregel")),
        sa.ForeignKeyConstraint(
            ["bestandteil_id"],
            ["bestandteil.id"],
            name=op.f("fk_zinsregel_bestandteil_id_bestandteil"),
        ),
        sa.ForeignKeyConstraint(
            ["konto_id"], ["konto.id"], name=op.f("fk_zinsregel_konto_id_konto")
        ),
        sa.UniqueConstraint("konto_id", name=op.f("uq_zinsregel_konto_id")),
        sa.CheckConstraint(_in("typ", ZINSREGELTYP), name=op.f("ck_zinsregel_typ")),
        sa.CheckConstraint(_in("quelle", QUELLEN_ZINSREGEL), name=op.f("ck_zinsregel_quelle")),
        sa.CheckConstraint(
            "(typ = 'keine') = (konto_id IS NULL)", name=op.f("ck_zinsregel_konto_nur_verzinslich")
        ),
        sa.CheckConstraint(
            "(typ = 'basiszins_plus') = (aufschlag IS NOT NULL)",
            name=op.f("ck_zinsregel_aufschlag"),
        ),
        sa.CheckConstraint("(typ = 'fest') = (satz IS NOT NULL)", name=op.f("ck_zinsregel_satz")),
        sa.CheckConstraint(
            "typ = 'keine' OR ab IS NOT NULL", name=op.f("ck_zinsregel_ab_verzinslich")
        ),
        sa.CheckConstraint(
            "typ <> 'keine' OR bis IS NULL", name=op.f("ck_zinsregel_bis_nicht_bei_keine")
        ),
        sa.CheckConstraint(
            "bis IS NULL OR ab IS NULL OR bis >= ab", name=op.f("ck_zinsregel_bis_nicht_vor_ab")
        ),
    )
    op.create_index(op.f("ix_zinsregel_bestandteil_id"), "zinsregel", ["bestandteil_id"])

    op.create_table(
        "ereignis",
        _uuid_pk(),
        sa.Column("akte_id", sa.Uuid(), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("buchung_id", sa.Uuid(), nullable=True),
        _zeitstempel("erfasst_am"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ereignis")),
        sa.ForeignKeyConstraint(["akte_id"], ["akte.id"], name=op.f("fk_ereignis_akte_id_akte")),
        sa.ForeignKeyConstraint(
            ["buchung_id"], ["buchung.id"], name=op.f("fk_ereignis_buchung_id_buchung")
        ),
        sa.UniqueConstraint("buchung_id", name=op.f("uq_ereignis_buchung_id")),
        sa.CheckConstraint("typ ~ '^[a-z_]+$'", name=op.f("ck_ereignis_typ_format")),
        sa.CheckConstraint(
            "(typ = 'zahlung') = (buchung_id IS NOT NULL)",
            name=op.f("ck_ereignis_buchung_bei_zahlung"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(details) = 'object'", name=op.f("ck_ereignis_details_objekt")
        ),
    )
    op.create_index(op.f("ix_ereignis_akte_id"), "ereignis", ["akte_id"])

    op.execute(EREIGNIS_FUNKTION)
    op.execute(EREIGNIS_TRIGGER)

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE"
        f" ON public.glaeubiger, public.zinsregel, public.ereignis TO {APP}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON public.akte TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON public.akte_teilungstag TO {APP}")
    op.execute(f"GRANT SELECT, INSERT ON public.akte_konto, public.bestandteil TO {APP}")
    op.execute(
        f"GRANT UPDATE (entstanden_am, faellig_am, kenntnis_am) ON public.bestandteil TO {APP}"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER ereignis_mit_buchung_unveraenderlich ON public.ereignis")
    op.execute("DROP FUNCTION public.verbindlichkeiten_ereignis_mit_buchung()")
    op.drop_table("ereignis")
    op.drop_table("zinsregel")
    op.drop_table("bestandteil")
    op.drop_table("akte_teilungstag")
    op.drop_table("akte_konto")
    op.drop_table("akte")
    op.drop_table("glaeubiger")
    op.drop_constraint(op.f("ck_haushalt_bundesland"), "haushalt", type_="check")
    op.drop_column("haushalt", "bundesland")
