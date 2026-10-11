# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buchungskern: haushalt, konto, buchung, posting mit ihren Invarianten.

Revision: 0001
Vorgänger: keiner

Umsetzung von Fachkonzept 4.4, E-17, E-18 und E-19:

- Zurückgestellt (DEFERRABLE INITIALLY DEFERRED, am Ende der Transaktion) je Buchung:
  mindestens zwei Postings auf mindestens zwei verschiedenen Konten, Summe null, alle Konten
  im Haushalt der Buchung; ein Storno besteht genau aus den negierten Postings des Originals.
- Sofort: Postings nur in der Transaktion ihrer Buchung, erkannt an der Transaktionsnummer
  (erfasst_txid); erfasst_am und erfasst_txid setzt die Datenbank; Storno nur von einer
  vorhandenen Buchung, die selbst kein Storno ist, im selben Haushalt und mit derselben
  Wertstellung; höchstens ein Storno je Buchung (eindeutiger Index).
- UPDATE, DELETE und TRUNCATE auf buchung und posting sind verboten; an konto sind die
  Stammfelder unveränderlich. Alle Trigger feuern immer (ENABLE ALWAYS).
- Die Laufzeitrolle darf nur lesen und einfügen.

Alle Namen sind ausgeschrieben, damit eine spätere Änderung der Namenskonvention diese
Migration nicht verändert. Die Funktionen sprechen Tabellen nur schemaqualifiziert an und
haben einen festen search_path. Die SQL-Texte enthalten weder Prozentzeichen noch
Doppelpunkt-Namen, weil op.execute sie als SQLAlchemy-Text verarbeitet.
"""

import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | tuple[str, ...] | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

NAMENSMUSTER = r"'^[a-z_]+\.[a-z_]+$'"


class _Xid8(sa.types.UserDefinedType[str]):
    """PostgreSQL xid8; eigene Klasse, damit die Migration nicht vom Code der App abhängt."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "xid8"


FUNKTIONEN = [
    # Zurückgestellte Prüfung einer Buchung; feuert für die Buchung und für jedes Posting.
    """
CREATE FUNCTION public.ledger_pruefe_buchung() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_buchung_id uuid;
    v_haushalt_id uuid;
    v_storno_von uuid;
    v_original uuid;
    v_storno uuid;
    v_anzahl bigint;
    v_konten bigint;
    v_summe numeric;
BEGIN
    IF TG_TABLE_NAME = 'buchung' THEN
        v_buchung_id := NEW.id;
    ELSE
        v_buchung_id := NEW.buchung_id;
    END IF;

    SELECT b.haushalt_id, b.storno_von INTO v_haushalt_id, v_storno_von
      FROM public.buchung AS b WHERE b.id = v_buchung_id;

    SELECT count(*), count(DISTINCT p.konto_id), coalesce(sum(p.betrag), 0)
      INTO v_anzahl, v_konten, v_summe
      FROM public.posting AS p WHERE p.buchung_id = v_buchung_id;

    IF v_anzahl < 2 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || v_buchung_id || ' hat weniger als zwei Postings.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'buchung_mindestens_zwei_postings', TABLE = 'buchung';
    END IF;
    IF v_konten < 2 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || v_buchung_id || ' bebucht nur ein Konto.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'buchung_mindestens_zwei_konten', TABLE = 'buchung';
    END IF;
    IF v_summe <> 0 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Die Postings der Buchung ' || v_buchung_id || ' ergeben nicht null.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'buchung_summe_null', TABLE = 'posting';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.posting AS p JOIN public.konto AS k ON k.id = p.konto_id
         WHERE p.buchung_id = v_buchung_id AND k.haushalt_id <> v_haushalt_id
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || v_buchung_id || ' bebucht Konten eines anderen Haushalts.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'buchung_ein_haushalt', TABLE = 'posting';
    END IF;
    -- Spiegelung in beide Richtungen: Geprüft wird das Storno und ebenso das Original, wenn
    -- es eines hat. Sonst entgingen ihr Postings, die das Original nach einer vorgezogenen
    -- Prüfung (SET CONSTRAINTS ... IMMEDIATE) in derselben Transaktion bekommt.
    IF v_storno_von IS NOT NULL THEN
        v_original := v_storno_von;
        v_storno := v_buchung_id;
    ELSE
        v_original := v_buchung_id;
        SELECT b.id INTO v_storno FROM public.buchung AS b WHERE b.storno_von = v_buchung_id;
    END IF;
    IF v_storno IS NOT NULL AND EXISTS (
        (SELECT p.konto_id, p.betrag FROM public.posting AS p
          WHERE p.buchung_id = v_storno
         EXCEPT ALL
         SELECT o.konto_id, -o.betrag FROM public.posting AS o
          WHERE o.buchung_id = v_original)
        UNION ALL
        (SELECT o.konto_id, -o.betrag FROM public.posting AS o
          WHERE o.buchung_id = v_original
         EXCEPT ALL
         SELECT p.konto_id, p.betrag FROM public.posting AS p
          WHERE p.buchung_id = v_storno)
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Storno ' || v_storno || ' negiert die Ursprungsbuchung nicht genau.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_spiegelbildlich', TABLE = 'posting';
    END IF;
    RETURN NULL;
END
$$
""",
    # Vor dem Einfügen einer Buchung: erfasst_am und erfasst_txid setzen, Storno-Regeln prüfen.
    # pg_current_xact_id() ist die Nummer der äußersten Transaktion, auch in einem Savepoint,
    # und wird nie wiederverwendet (64 Bit).
    """
CREATE FUNCTION public.ledger_buchung_vor_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_haushalt_id uuid;
    v_wertstellung date;
    v_storno_von uuid;
BEGIN
    NEW.erfasst_am := now();
    NEW.erfasst_txid := pg_current_xact_id();
    IF NEW.storno_von IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT b.haushalt_id, b.wertstellung, b.storno_von
      INTO v_haushalt_id, v_wertstellung, v_storno_von
      FROM public.buchung AS b WHERE b.id = NEW.storno_von;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Die zu stornierende Buchung ' || NEW.storno_von || ' gibt es nicht.',
            ERRCODE = 'foreign_key_violation',
            CONSTRAINT = 'storno_original', TABLE = 'buchung';
    END IF;
    IF v_storno_von IS NOT NULL THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || NEW.storno_von || ' ist selbst ein Storno.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_nicht_von_storno', TABLE = 'buchung';
    END IF;
    IF v_haushalt_id <> NEW.haushalt_id THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Storno und Buchung ' || NEW.storno_von || ' liegen in zwei Haushalten.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_gleicher_haushalt', TABLE = 'buchung';
    END IF;
    IF v_wertstellung <> NEW.wertstellung THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Ein Storno hat die Wertstellung der Buchung ' || NEW.storno_von || '.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_gleiche_wertstellung', TABLE = 'buchung';
    END IF;
    RETURN NEW;
END
$$
""",
    # Vor dem Einfügen eines Postings: Die Buchung muss in dieser Transaktion entstanden sein.
    # Findet der Trigger sie nicht (noch nicht committet, zurückgerollt oder erst später in
    # derselben Anweisung), ist v_erfasst_txid NULL und das Posting wird ebenfalls abgelehnt;
    # der Fremdschlüssel prüft nur, dass es die Buchung am Ende der Anweisung gibt.
    """
CREATE FUNCTION public.ledger_posting_vor_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_erfasst_txid xid8;
BEGIN
    SELECT b.erfasst_txid INTO v_erfasst_txid
      FROM public.buchung AS b WHERE b.id = NEW.buchung_id;
    IF v_erfasst_txid IS DISTINCT FROM pg_current_xact_id() THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || NEW.buchung_id || ' ist nicht in dieser Transaktion'
                || ' entstanden; Postings entstehen nur mit ihrer Buchung.',
            ERRCODE = 'restrict_violation',
            CONSTRAINT = 'buchung_abgeschlossen', TABLE = 'posting';
    END IF;
    RETURN NEW;
END
$$
""",
    # UPDATE, DELETE und TRUNCATE auf buchung und posting; je Anweisung, also auch bei null
    # betroffenen Zeilen und bei INSERT … ON CONFLICT DO UPDATE.
    """
CREATE FUNCTION public.ledger_unveraenderlich() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = TG_OP || ' auf ' || TG_TABLE_NAME
            || ' ist verboten; Korrekturen nur durch Storno und Neubuchung.',
        ERRCODE = 'restrict_violation',
        CONSTRAINT = TG_TABLE_NAME || '_unveraenderlich', TABLE = TG_TABLE_NAME;
END
$$
""",
    # An einem Konto ist nur die Bezeichnung änderbar.
    """
CREATE FUNCTION public.ledger_konto_vor_update() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF (NEW.id, NEW.haushalt_id, NEW.kontoart, NEW.rolle, NEW.waehrung)
       IS DISTINCT FROM (OLD.id, OLD.haushalt_id, OLD.kontoart, OLD.rolle, OLD.waehrung) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'An einem Konto ist nur die Bezeichnung änderbar.',
            ERRCODE = 'restrict_violation',
            CONSTRAINT = 'konto_stammdaten_unveraenderlich', TABLE = 'konto';
    END IF;
    RETURN NEW;
END
$$
""",
]

TRIGGER = [
    "CREATE TRIGGER buchung_vor_insert BEFORE INSERT ON public.buchung"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_buchung_vor_insert()",
    "CREATE CONSTRAINT TRIGGER buchung_pruefen AFTER INSERT ON public.buchung"
    " DEFERRABLE INITIALLY DEFERRED"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_pruefe_buchung()",
    "CREATE TRIGGER posting_vor_insert BEFORE INSERT ON public.posting"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_posting_vor_insert()",
    "CREATE CONSTRAINT TRIGGER posting_pruefen AFTER INSERT ON public.posting"
    " DEFERRABLE INITIALLY DEFERRED"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_pruefe_buchung()",
    "CREATE TRIGGER buchung_unveraenderlich"
    " BEFORE UPDATE OR DELETE OR TRUNCATE ON public.buchung"
    " FOR EACH STATEMENT EXECUTE FUNCTION public.ledger_unveraenderlich()",
    "CREATE TRIGGER posting_unveraenderlich"
    " BEFORE UPDATE OR DELETE OR TRUNCATE ON public.posting"
    " FOR EACH STATEMENT EXECUTE FUNCTION public.ledger_unveraenderlich()",
    "CREATE TRIGGER konto_vor_update BEFORE UPDATE ON public.konto"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_konto_vor_update()",
    # ENABLE ALWAYS: Die Trigger feuern auch bei session_replication_role = replica.
    "ALTER TABLE public.buchung ENABLE ALWAYS TRIGGER buchung_vor_insert",
    "ALTER TABLE public.buchung ENABLE ALWAYS TRIGGER buchung_pruefen",
    "ALTER TABLE public.buchung ENABLE ALWAYS TRIGGER buchung_unveraenderlich",
    "ALTER TABLE public.posting ENABLE ALWAYS TRIGGER posting_vor_insert",
    "ALTER TABLE public.posting ENABLE ALWAYS TRIGGER posting_pruefen",
    "ALTER TABLE public.posting ENABLE ALWAYS TRIGGER posting_unveraenderlich",
    "ALTER TABLE public.konto ENABLE ALWAYS TRIGGER konto_vor_update",
]

FUNKTIONSNAMEN = (
    "ledger_pruefe_buchung",
    "ledger_buchung_vor_insert",
    "ledger_posting_vor_insert",
    "ledger_unveraenderlich",
    "ledger_konto_vor_update",
)


def _uuid_pk() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "haushalt",
        _uuid_pk(),
        sa.Column("betriebsart", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_haushalt")),
        sa.CheckConstraint(
            "betriebsart IN ('einzel', 'haushalt_gemeinsam', 'haushalt_getrennt')",
            name=op.f("ck_haushalt_betriebsart"),
        ),
    )
    op.create_table(
        "konto",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("kontoart", sa.Text(), nullable=False),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("waehrung", sa.CHAR(3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_konto")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_konto_haushalt_id_haushalt")
        ),
        sa.CheckConstraint(
            "kontoart IN ('aktiv', 'passiv', 'aufwand', 'ertrag', 'eigenkapital')",
            name=op.f("ck_konto_kontoart"),
        ),
        sa.CheckConstraint(f"rolle ~ {NAMENSMUSTER}", name=op.f("ck_konto_rolle_format")),
        sa.CheckConstraint("waehrung = 'EUR'", name=op.f("ck_konto_nur_eur")),
    )
    op.create_index(op.f("ix_konto_haushalt_id"), "konto", ["haushalt_id"])
    op.create_table(
        "buchung",
        _uuid_pk(),
        sa.Column("haushalt_id", sa.Uuid(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("wertstellung", sa.Date(), nullable=False),
        sa.Column(
            "erfasst_am",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("erfasst_txid", _Xid8(), nullable=False),
        sa.Column("storno_von", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buchung")),
        sa.ForeignKeyConstraint(
            ["haushalt_id"], ["haushalt.id"], name=op.f("fk_buchung_haushalt_id_haushalt")
        ),
        sa.ForeignKeyConstraint(
            ["storno_von"], ["buchung.id"], name=op.f("fk_buchung_storno_von_buchung")
        ),
        sa.UniqueConstraint("storno_von", name=op.f("uq_buchung_storno_von")),
        sa.CheckConstraint(f"art ~ {NAMENSMUSTER}", name=op.f("ck_buchung_art_format")),
        sa.CheckConstraint(
            "(art = 'kern.storno') = (storno_von IS NOT NULL)", name=op.f("ck_buchung_storno_art")
        ),
        sa.CheckConstraint("storno_von <> id", name=op.f("ck_buchung_storno_nicht_selbst")),
    )
    op.create_table(
        "posting",
        _uuid_pk(),
        sa.Column("buchung_id", sa.Uuid(), nullable=False),
        sa.Column("konto_id", sa.Uuid(), nullable=False),
        sa.Column("betrag", sa.Numeric(19, 4), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting")),
        sa.ForeignKeyConstraint(
            ["buchung_id"], ["buchung.id"], name=op.f("fk_posting_buchung_id_buchung")
        ),
        sa.ForeignKeyConstraint(["konto_id"], ["konto.id"], name=op.f("fk_posting_konto_id_konto")),
        sa.CheckConstraint("betrag <> 0", name=op.f("ck_posting_betrag_ungleich_null")),
    )
    op.create_index(op.f("ix_posting_buchung_id"), "posting", ["buchung_id"])
    op.create_index(op.f("ix_posting_konto_id"), "posting", ["konto_id"])

    for anweisung in FUNKTIONEN + TRIGGER:
        op.execute(anweisung)

    # Rechte der Laufzeitrolle (E-19): nur lesen und einfügen.
    op.execute(
        "GRANT SELECT, INSERT ON public.haushalt, public.konto, public.buchung, public.posting"
        " TO finanzmanager_app"
    )


def downgrade() -> None:
    # DROP TABLE ist weder DELETE noch TRUNCATE; die Trigger hielten es nicht auf.
    op.execute(
        "DO $$ BEGIN"
        " IF EXISTS (SELECT 1 FROM public.buchung) THEN"
        " RAISE EXCEPTION USING"
        " MESSAGE = 'Rückweg von 0001 würde Buchungen löschen; abgebrochen.',"
        " ERRCODE = 'object_not_in_prerequisite_state';"
        " END IF;"
        " END $$"
    )
    op.drop_table("posting")
    op.drop_table("buchung")
    op.drop_table("konto")
    op.drop_table("haushalt")
    for funktion in FUNKTIONSNAMEN:
        op.execute(sa.text("DROP FUNCTION public." + funktion + "()"))
