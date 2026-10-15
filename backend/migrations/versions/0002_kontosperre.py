# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buchungsdatum, Stornoschutz und Kontosperre.

Revision: 0002
Vorgänger: 0001

Umsetzung von Fachkonzept 4.4, E-26, E-27 und E-28:

- buchung.buchungsdatum ordnet eine Buchung einem Zeitraum zu; es liegt nie vor der
  Wertstellung. Bestehende Buchungen bekommen ihre Wertstellung als Buchungsdatum, ohne
  UPDATE: Die Spalte entsteht als generierte Spalte, PostgreSQL berechnet sie beim
  Umschreiben der Tabelle, und DROP EXPRESSION macht sie zu einer normalen Spalte. Das ist
  fachlich richtig, weil es vor dieser Migration keine Festschreibung gibt; jede Buchung
  liegt im offenen Zeitraum (E-26). Kein Trigger wird abgeschaltet.
- buchung.stornierbar: beim Einfügen gesetzt, danach unveränderlich wie die ganze Buchung.
  Ein Storno setzt voraus, dass die Ursprungsbuchung stornierbar ist, und sein
  Buchungsdatum liegt nicht vor dem der Ursprungsbuchung (E-28).
- konto_sperre: je Konto ein Sperrdatum, nur anhängend. Ein Posting auf ein Konto, dessen
  Buchung ein Buchungsdatum am oder vor dem Sperrdatum hat, wird abgelehnt (E-27).

Nebenläufigkeit (Fachkonzept 4.4): Jedes Posting hält sein Konto mit einer geteilten,
jede Sperre mit einer exklusiven Advisory-Sperre bis zum Ende der Transaktion, in der
zweistelligen Form mit dem Namensraum der Kontosperre. Beide werden nur versucht
(pg_try_advisory_xact_lock…): Wer sie nicht bekommt, scheitert sofort mit 55P03, ohne
Wartezeit und ohne Deadlock. Erst danach liest der Trigger das Sperrdatum; in READ
COMMITTED sieht er damit jede bis dahin committete Sperre. In REPEATABLE READ und
SERIALIZABLE sähe eine Transaktion eine später committete Sperre nicht; deshalb nehmen
Postings und Sperren nur READ COMMITTED an.

Die Funktionen sprechen Tabellen nur schemaqualifiziert an und haben einen festen
search_path. Die SQL-Texte enthalten weder Prozentzeichen noch Doppelpunkt-Namen, weil
op.execute sie als SQLAlchemy-Text verarbeitet.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | tuple[str, ...] | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

# Namensraum der Kontosperre für pg_advisory_xact_lock(int4, int4): 0x4B535052, ASCII
# „KSPR“. Andere Nutzer von Advisory-Sperren wählen einen anderen Namensraum. Im
# Namensraum steht der Hash der Konto-ID (hashtext); kollidieren zwei Konten, scheitert
# höchstens eine Buchung unnötig und wird wiederholt, eine Sperre geht nie verloren.
NAMENSRAUM = 1263751250

NUR_READ_COMMITTED = """
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchungen und Kontosperren nur in READ COMMITTED (Fachkonzept 4.4).',
            ERRCODE = 'invalid_transaction_state',
            CONSTRAINT = 'nur_read_committed';
    END IF;
"""

FUNKTIONEN = [
    # Schlüssel eines Kontos im Namensraum der Kontosperre.
    """
CREATE FUNCTION public.ledger_konto_sperrschluessel(p_konto_id uuid) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog, pg_temp AS $$
    SELECT pg_catalog.hashtext(CAST(p_konto_id AS text))
$$
""",
    # Exklusiv halten, bis die Transaktion endet; scheitert sofort, wenn eine andere
    # Transaktion auf dem Konto bucht oder es hält. Die Kern-API ruft sie vor einer
    # Festschreibung auf, damit diese auf genau den Postings rechnet, die ihre Sperre
    # einfriert (Fachkonzept 5.2 Schritt 7).
    f"""
CREATE FUNCTION public.ledger_halte_konto(p_konto_id uuid) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
{NUR_READ_COMMITTED}
    IF NOT pg_try_advisory_xact_lock(
        {NAMENSRAUM}, public.ledger_konto_sperrschluessel(p_konto_id)
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Eine andere Transaktion bucht gerade auf dem Konto ' || p_konto_id
                || ' oder hält es.',
            ERRCODE = 'lock_not_available',
            CONSTRAINT = 'konto_wird_bebucht', TABLE = 'konto';
    END IF;
END
$$
""",
    # Vor dem Einfügen einer Sperre: erfasst_am setzen, Konto exklusiv halten, Sperrdatum
    # steigt nur. Gelesen wird erst nach der Advisory-Sperre.
    """
CREATE FUNCTION public.ledger_konto_sperre_vor_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_gesperrt_bis date;
BEGIN
    NEW.erfasst_am := now();
    PERFORM public.ledger_halte_konto(NEW.konto_id);
    SELECT max(s.gesperrt_bis) INTO v_gesperrt_bis
      FROM public.konto_sperre AS s WHERE s.konto_id = NEW.konto_id;
    IF NEW.gesperrt_bis <= v_gesperrt_bis THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Das Sperrdatum von Konto ' || NEW.konto_id || ' steigt nur; bisher '
                || v_gesperrt_bis || '.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'konto_sperre_steigt', TABLE = 'konto_sperre';
    END IF;
    RETURN NEW;
END
$$
""",
    # UPDATE, DELETE und TRUNCATE auf konto_sperre; je Anweisung.
    """
CREATE FUNCTION public.ledger_konto_sperre_unveraenderlich() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = TG_OP || ' auf konto_sperre ist verboten; ein Sperrdatum steigt nur'
            || ' durch eine neue Zeile.',
        ERRCODE = 'restrict_violation',
        CONSTRAINT = 'konto_sperre_unveraenderlich', TABLE = 'konto_sperre';
END
$$
""",
]

# Neue Fassungen der Funktionen aus 0001.
ERSETZT = [
    # Wie 0001, dazu der Stornoschutz (E-28).
    """
CREATE OR REPLACE FUNCTION public.ledger_buchung_vor_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_haushalt_id uuid;
    v_wertstellung date;
    v_storno_von uuid;
    v_stornierbar boolean;
    v_buchungsdatum date;
BEGIN
    NEW.erfasst_am := now();
    NEW.erfasst_txid := pg_current_xact_id();
    IF NEW.storno_von IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT b.haushalt_id, b.wertstellung, b.storno_von, b.stornierbar, b.buchungsdatum
      INTO v_haushalt_id, v_wertstellung, v_storno_von, v_stornierbar, v_buchungsdatum
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
    IF NOT v_stornierbar THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || NEW.storno_von || ' ist nicht stornierbar.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_stornierbar', TABLE = 'buchung';
    END IF;
    IF NEW.buchungsdatum < v_buchungsdatum THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Das Buchungsdatum eines Stornos liegt nicht vor dem der Buchung '
                || NEW.storno_von || '.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'storno_buchungsdatum', TABLE = 'buchung';
    END IF;
    RETURN NEW;
END
$$
""",
    # Wie 0001, dazu die Kontosperre (E-27): erst die geteilte Advisory-Sperre, dann das
    # Sperrdatum lesen. Eingesetzt werden nur Konstanten dieser Datei.
    f"""
CREATE OR REPLACE FUNCTION public.ledger_posting_vor_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_erfasst_txid xid8;
    v_buchungsdatum date;
    v_gesperrt_bis date;
BEGIN
    SELECT b.erfasst_txid, b.buchungsdatum INTO v_erfasst_txid, v_buchungsdatum
      FROM public.buchung AS b WHERE b.id = NEW.buchung_id;
    IF v_erfasst_txid IS DISTINCT FROM pg_current_xact_id() THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Buchung ' || NEW.buchung_id || ' ist nicht in dieser Transaktion'
                || ' entstanden; Postings entstehen nur mit ihrer Buchung.',
            ERRCODE = 'restrict_violation',
            CONSTRAINT = 'buchung_abgeschlossen', TABLE = 'posting';
    END IF;
{NUR_READ_COMMITTED}
    IF NOT pg_try_advisory_xact_lock_shared(
        {NAMENSRAUM}, public.ledger_konto_sperrschluessel(NEW.konto_id)
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Eine andere Transaktion hält das Konto ' || NEW.konto_id || ' gerade.',
            ERRCODE = 'lock_not_available',
            CONSTRAINT = 'konto_wird_gesperrt', TABLE = 'posting';
    END IF;
    SELECT max(s.gesperrt_bis) INTO v_gesperrt_bis
      FROM public.konto_sperre AS s WHERE s.konto_id = NEW.konto_id;
    IF v_buchungsdatum <= v_gesperrt_bis THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Konto ' || NEW.konto_id || ' ist bis ' || v_gesperrt_bis
                || ' gesperrt; das Buchungsdatum muss danach liegen.',
            ERRCODE = 'check_violation',
            CONSTRAINT = 'posting_konto_gesperrt', TABLE = 'posting';
    END IF;
    RETURN NEW;
END
$$
""",  # noqa: S608
]

# Die Fassungen aus 0001, für den Rückweg wörtlich übernommen: Migrationen importieren
# einander nicht, und 0001 bleibt unverändert.
FASSUNGEN_0001 = [
    """
CREATE OR REPLACE FUNCTION public.ledger_buchung_vor_insert() RETURNS trigger
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
    """
CREATE OR REPLACE FUNCTION public.ledger_posting_vor_insert() RETURNS trigger
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
]

TRIGGER = [
    "CREATE TRIGGER konto_sperre_vor_insert BEFORE INSERT ON public.konto_sperre"
    " FOR EACH ROW EXECUTE FUNCTION public.ledger_konto_sperre_vor_insert()",
    "CREATE TRIGGER konto_sperre_unveraenderlich"
    " BEFORE UPDATE OR DELETE OR TRUNCATE ON public.konto_sperre"
    " FOR EACH STATEMENT EXECUTE FUNCTION public.ledger_konto_sperre_unveraenderlich()",
    # ENABLE ALWAYS: Die Trigger feuern auch bei session_replication_role = replica.
    "ALTER TABLE public.konto_sperre ENABLE ALWAYS TRIGGER konto_sperre_vor_insert",
    "ALTER TABLE public.konto_sperre ENABLE ALWAYS TRIGGER konto_sperre_unveraenderlich",
]

NEUE_FUNKTIONEN = (
    "ledger_konto_sperre_vor_insert()",
    "ledger_konto_sperre_unveraenderlich()",
    "ledger_halte_konto(uuid)",
    "ledger_konto_sperrschluessel(uuid)",
)


def upgrade() -> None:
    # Buchungsdatum ohne UPDATE füllen (siehe Modul-Docstring).
    op.execute(
        "ALTER TABLE public.buchung"
        " ADD COLUMN buchungsdatum date GENERATED ALWAYS AS (wertstellung) STORED"
    )
    op.execute("ALTER TABLE public.buchung ALTER COLUMN buchungsdatum DROP EXPRESSION")
    op.execute("ALTER TABLE public.buchung ALTER COLUMN buchungsdatum SET NOT NULL")
    op.create_check_constraint(
        op.f("ck_buchung_buchungsdatum_nicht_vor_wertstellung"),
        "buchung",
        "buchungsdatum >= wertstellung",
    )
    # Konstanter Default: PostgreSQL trägt ihn für bestehende Zeilen im Katalog ein.
    op.add_column(
        "buchung",
        sa.Column("stornierbar", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "konto_sperre",
        sa.Column("konto_id", sa.Uuid(), nullable=False),
        sa.Column("gesperrt_bis", sa.Date(), nullable=False),
        sa.Column(
            "erfasst_am",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("konto_id", "gesperrt_bis", name=op.f("pk_konto_sperre")),
        sa.ForeignKeyConstraint(
            ["konto_id"], ["konto.id"], name=op.f("fk_konto_sperre_konto_id_konto")
        ),
    )

    for anweisung in FUNKTIONEN + ERSETZT + TRIGGER:
        op.execute(anweisung)

    # Rechte der Laufzeitrolle (E-19): nur lesen und einfügen.
    op.execute("GRANT SELECT, INSERT ON public.konto_sperre TO finanzmanager_app")


def downgrade() -> None:
    # Sperren, Stornoschutz und abweichende Buchungsdaten gingen verloren; dann nicht. Die
    # Tabellen werden vorher exklusiv gesperrt, damit keine gleichzeitige Transaktion nach
    # der Prüfung noch solche Daten committet.
    op.execute("LOCK TABLE public.buchung, public.konto_sperre IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ BEGIN"
        " IF EXISTS (SELECT 1 FROM public.konto_sperre)"
        " OR EXISTS (SELECT 1 FROM public.buchung"
        " WHERE NOT stornierbar OR buchungsdatum <> wertstellung) THEN"
        " RAISE EXCEPTION USING"
        " MESSAGE = 'Rückweg von 0002 würde Sperren, Stornoschutz oder Buchungsdaten"
        " verlieren; abgebrochen.',"
        " ERRCODE = 'object_not_in_prerequisite_state';"
        " END IF;"
        " END $$"
    )
    op.drop_table("konto_sperre")
    for anweisung in FASSUNGEN_0001:
        op.execute(anweisung)
    for funktion in NEUE_FUNKTIONEN:
        op.execute(sa.text("DROP FUNCTION public." + funktion))
    op.drop_column("buchung", "stornierbar")
    op.drop_constraint(
        op.f("ck_buchung_buchungsdatum_nicht_vor_wertstellung"), "buchung", type_="check"
    )
    op.drop_column("buchung", "buchungsdatum")
