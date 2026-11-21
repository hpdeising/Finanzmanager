// SPDX-License-Identifier: AGPL-3.0-or-later
// Eine Akte zum Stichtag: Restschuld, Status, Fristen, Verjährung, Bestandteile, Ereignisse
// und Rechenweg. Alles wird bei jeder Abfrage neu berechnet (Fachkonzept E-21).
import { useCallback, useEffect, useState } from "react";

import { api, fehlertext, type Schemas } from "../../kern/api/client";
import { formatiereDatum, heute } from "../../kern/datum";
import { formatiereBetrag } from "../../kern/geld";
import { Meldung } from "../../kern/Meldung";
import { BestandteilFormular, EreignisFormular, ZahlungFormular } from "./formulare";
import { AUFGABE, BESTANDTEILART, EREIGNISTYP, FRISTART, MERKMAL, STATUS } from "./texte";

type Detail = Schemas["AkteDetail"];

function Zeile({ name, wert }: { name: string; wert: string }) {
  return (
    <div className="kern-description-list-item">
      <dt className="kern-description-list-item__key">{name}</dt>
      <dd className="kern-description-list-item__value">{wert}</dd>
    </div>
  );
}

export function Akte({ id }: { id: string }) {
  const [stichtag, setStichtag] = useState(heute());
  const [akte, setAkte] = useState<Detail | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const lade = useCallback(() => {
    void api
      .GET("/api/verbindlichkeiten/akten/{akte_id}", {
        params: { path: { akte_id: id }, query: { stichtag } },
      })
      .then(({ data, error }) => {
        if (error) {
          setFehler(fehlertext(error));
        } else {
          setFehler(null);
          setAkte(data);
        }
      });
  }, [id, stichtag]);
  useEffect(lade, [lade]);

  async function storniere(ereignisId: string) {
    const { error } = await api.POST(
      "/api/verbindlichkeiten/akten/{akte_id}/zahlungen/{ereignis_id}/storno",
      { params: { path: { akte_id: id, ereignis_id: ereignisId } } },
    );
    if (error) {
      setFehler(fehlertext(error));
    }
    lade();
  }

  async function loesche(ereignisId: string) {
    const { error } = await api.DELETE(
      "/api/verbindlichkeiten/akten/{akte_id}/ereignisse/{ereignis_id}",
      { params: { path: { akte_id: id, ereignis_id: ereignisId } } },
    );
    if (error) {
      setFehler(fehlertext(error));
    }
    lade();
  }

  if (akte === null) {
    return fehler ? <Meldung art="danger">{fehler}</Meldung> : <p className="kern-body">Lädt …</p>;
  }
  const b = akte.berechnung;
  const s = akte.status;

  return (
    <article className="kern-stack">
      <hgroup className="kern-hgroup">
        <h1 className="kern-heading-large">{akte.glaeubiger_name}</h1>
        <p className="kern-subline">
          Aktenzeichen {akte.aktenzeichen_glaeubiger ?? "–"}
          {akte.verbraucherdarlehen ? " · Verbraucherdarlehen" : ""}
        </p>
      </hgroup>
      {fehler && <Meldung art="danger">{fehler}</Meldung>}

      <div className="kern-form-input">
        <label className="kern-label" htmlFor="stichtag">
          Stichtag
        </label>
        <input
          id="stichtag"
          type="date"
          className="kern-form-input__input"
          value={stichtag}
          onChange={(e) => e.target.value && setStichtag(e.target.value)}
        />
      </div>

      {akte.hinweise.map((hinweis) => (
        <Meldung art="warning" key={hinweis}>
          {hinweis}
        </Meldung>
      ))}

      <section aria-labelledby="ueberblick" className="kern-stack">
        <h2 className="kern-heading-medium" id="ueberblick">
          Überblick zum {formatiereDatum(akte.stichtag)}
        </h2>
        <dl className="kern-description-list">
          <Zeile name="Status" wert={s ? STATUS[s.status] : "nicht berechenbar"} />
          {b && (
            <>
              <Zeile name="Restschuld" wert={formatiereBetrag(b.restschuld)} />
              <Zeile name="Hauptforderung" wert={formatiereBetrag(b.hauptforderung)} />
              <Zeile name="Zinsen" wert={formatiereBetrag(b.zinsen)} />
              <Zeile name="Kosten" wert={formatiereBetrag(b.kosten)} />
              <Zeile name="Überzahlung" wert={formatiereBetrag(b.ueberzahlung)} />
            </>
          )}
          {s && s.merkmale.length > 0 && (
            <Zeile name="Merkmale" wert={s.merkmale.map((m) => MERKMAL[m]).join(", ")} />
          )}
        </dl>
        {s?.hinweise.map((h) => (
          <Meldung art="warning" key={h}>
            {h}
          </Meldung>
        ))}
        {s?.warnungen.map((w) => (
          <Meldung art="warning" key={w}>
            {w}
          </Meldung>
        ))}
      </section>

      {s && s.aufgaben.length > 0 && (
        <section aria-labelledby="aufgaben" className="kern-stack">
          <h2 className="kern-heading-medium" id="aufgaben">
            Nachwirkungs-Aufgaben
          </h2>
          <ul className="kern-list">
            {s.aufgaben.map((a) => (
              <li key={a.typ}>
                {AUFGABE[a.typ]} ({a.norm}):{" "}
                {a.information
                  ? "Information"
                  : a.erledigt_am
                    ? `erledigt am ${formatiereDatum(a.erledigt_am)}`
                    : `offen, fällig ab ${formatiereDatum(a.faellig_ab)}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="fristen" className="kern-stack">
        <h2 className="kern-heading-medium" id="fristen">
          Fristen
        </h2>
        {akte.fristen && akte.fristen.length > 0 ? (
          <div className="kern-table-responsive">
            <table className="kern-table">
              <thead className="kern-table__header">
                <tr>
                  <th scope="col">Frist</th>
                  <th scope="col">Ende</th>
                  <th scope="col">Art</th>
                  <th scope="col">Norm</th>
                  <th scope="col">Hinweis</th>
                </tr>
              </thead>
              <tbody className="kern-table__body">
                {akte.fristen.map((f) => (
                  <tr key={`${f.name}-${f.ende}`}>
                    <td className="kern-table__cell">{f.name}</td>
                    <td className="kern-table__cell">{formatiereDatum(f.ende)}</td>
                    <td className="kern-table__cell">{FRISTART[f.art]}</td>
                    <td className="kern-table__cell">{f.norm}</td>
                    <td className="kern-table__cell">{f.hinweis ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="kern-body">Keine Fristen.</p>
        )}
      </section>

      <section aria-labelledby="verjaehrung" className="kern-stack">
        <h2 className="kern-heading-medium" id="verjaehrung">
          Verjährung
        </h2>
        <Meldung art="info">{akte.verjaehrung_pflichthinweis}</Meldung>
        {akte.verjaehrung && akte.verjaehrung.length > 0 && (
          <div className="kern-table-responsive">
            <table className="kern-table">
              <thead className="kern-table__header">
                <tr>
                  <th scope="col">Gegenstand</th>
                  <th scope="col">Ende</th>
                  <th scope="col">Norm</th>
                  <th scope="col">Hinweise</th>
                </tr>
              </thead>
              <tbody className="kern-table__body">
                {akte.verjaehrung.map((v) => (
                  <tr key={v.gegenstand}>
                    <td className="kern-table__cell">{v.gegenstand}</td>
                    <td className="kern-table__cell">
                      {v.ende ? formatiereDatum(v.ende) : "offen"}
                    </td>
                    <td className="kern-table__cell">{v.norm}</td>
                    <td className="kern-table__cell">{v.hinweise.join(" ") || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="bestandteile" className="kern-stack">
        <h2 className="kern-heading-medium" id="bestandteile">
          Bestandteile
        </h2>
        {akte.bestandteile.length > 0 && (
          <ul className="kern-list">
            {akte.bestandteile.map((t) => (
              <li key={t.kennung}>
                {t.kennung}: {BESTANDTEILART[t.art]}, {formatiereBetrag(t.betrag)}, entstanden am{" "}
                {formatiereDatum(t.entstanden_am)}
              </li>
            ))}
          </ul>
        )}
        <BestandteilFormular akteId={id} fertig={lade} />
      </section>

      <section aria-labelledby="ereignisse" className="kern-stack">
        <h2 className="kern-heading-medium" id="ereignisse">
          Ereignisse und Zahlungen
        </h2>
        {akte.ereignisse.length > 0 && (
          <div className="kern-table-responsive">
            <table className="kern-table">
              <thead className="kern-table__header">
                <tr>
                  <th scope="col">Datum</th>
                  <th scope="col">Ereignis</th>
                  <th scope="col" className="kern-table__header--numeric">
                    Betrag
                  </th>
                  <th scope="col" className="kern-table__header--action">
                    Korrektur
                  </th>
                </tr>
              </thead>
              <tbody className="kern-table__body">
                {akte.ereignisse.map((e) => (
                  <tr key={e.id}>
                    <td className="kern-table__cell">{formatiereDatum(e.datum)}</td>
                    <td className="kern-table__cell">
                      {EREIGNISTYP[e.typ]}
                      {e.storniert ? " (storniert)" : ""}
                    </td>
                    <td className="kern-table__cell kern-table__cell--numeric">
                      {e.betrag ? formatiereBetrag(e.betrag) : "–"}
                    </td>
                    <td className="kern-table__cell kern-table__cell--action">
                      {e.typ === "zahlung" && !e.storniert && (
                        <button
                          type="button"
                          className="kern-btn kern-btn--tertiary kern-btn--small"
                          onClick={() => void storniere(e.id)}
                        >
                          <span className="kern-label">Stornieren</span>
                        </button>
                      )}
                      {e.typ !== "zahlung" && (
                        <button
                          type="button"
                          className="kern-btn kern-btn--tertiary kern-btn--small"
                          onClick={() => void loesche(e.id)}
                        >
                          <span className="kern-label">Löschen</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <h3 className="kern-heading-small">Zahlung erfassen</h3>
        <ZahlungFormular akteId={id} fertig={lade} />
        <h3 className="kern-heading-small">Ereignis erfassen</h3>
        <EreignisFormular akteId={id} fertig={lade} />
      </section>

      {b && b.abschnitte.length > 0 && (
        <details className="kern-details">
          <summary className="kern-details__header">
            <span className="kern-title">Rechenweg der Zinsen</span>
          </summary>
          <div className="kern-details__body kern-table-responsive">
            <table className="kern-table kern-table--small">
              <thead className="kern-table__header">
                <tr>
                  <th scope="col">Bestandteil</th>
                  <th scope="col">Von</th>
                  <th scope="col">Bis</th>
                  <th scope="col" className="kern-table__header--numeric">
                    Tage
                  </th>
                  <th scope="col" className="kern-table__header--numeric">
                    Basis
                  </th>
                  <th scope="col" className="kern-table__header--numeric">
                    Satz in %
                  </th>
                  <th scope="col" className="kern-table__header--numeric">
                    Zins
                  </th>
                </tr>
              </thead>
              <tbody className="kern-table__body">
                {b.abschnitte.map((a) => (
                  <tr key={`${a.bestandteil}-${a.von}`}>
                    <td className="kern-table__cell">{a.bestandteil}</td>
                    <td className="kern-table__cell">{formatiereDatum(a.von)}</td>
                    <td className="kern-table__cell">{formatiereDatum(a.bis)}</td>
                    <td className="kern-table__cell kern-table__cell--numeric">{a.tage}</td>
                    <td className="kern-table__cell kern-table__cell--numeric">
                      {formatiereBetrag(a.basis)}
                    </td>
                    <td className="kern-table__cell kern-table__cell--numeric">
                      {a.satz.replace(".", ",")}
                    </td>
                    <td className="kern-table__cell kern-table__cell--numeric">
                      {formatiereBetrag(a.zins)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </article>
  );
}
