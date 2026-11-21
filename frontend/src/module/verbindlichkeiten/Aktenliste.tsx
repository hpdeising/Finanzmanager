// SPDX-License-Identifier: AGPL-3.0-or-later
// Liste der Akten des Haushalts mit Status und Restschuld zum heutigen Tag.
import { useCallback, useEffect, useState } from "react";

import { api, fehlertext, type Schemas } from "../../kern/api/client";
import { formatiereBetrag } from "../../kern/geld";
import { Meldung } from "../../kern/Meldung";
import { NeueAkte } from "./NeueAkte";
import { STATUS } from "./texte";

export function Aktenliste() {
  const [akten, setAkten] = useState<Schemas["AktenZeile"][] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const lade = useCallback(() => {
    void api.GET("/api/verbindlichkeiten/akten").then(({ data, error }) => {
      if (error) {
        setFehler(fehlertext(error));
      } else {
        setAkten(data);
      }
    });
  }, []);
  useEffect(lade, [lade]);

  return (
    <section className="kern-stack">
      <h1 className="kern-heading-large">Akten</h1>
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      {akten === null && !fehler && <p className="kern-body">Lädt …</p>}
      {akten !== null && akten.length === 0 && (
        <p className="kern-body">Noch keine Akte. Lege unten die erste an.</p>
      )}
      {akten !== null && akten.length > 0 && (
        <div className="kern-table-responsive">
          <table className="kern-table">
            <caption className="kern-title">Akten mit Status und Restschuld zum heutigen Tag</caption>
            <thead className="kern-table__header">
              <tr>
                <th scope="col">Gläubiger</th>
                <th scope="col">Aktenzeichen</th>
                <th scope="col">Status</th>
                <th scope="col" className="kern-table__header--numeric">
                  Restschuld
                </th>
              </tr>
            </thead>
            <tbody className="kern-table__body">
              {akten.map((akte) => (
                <tr key={akte.id}>
                  <td className="kern-table__cell">
                    <a className="kern-link" href={`#/akten/${akte.id}`}>
                      {akte.glaeubiger_name}
                    </a>
                  </td>
                  <td className="kern-table__cell">{akte.aktenzeichen_glaeubiger ?? "–"}</td>
                  <td className="kern-table__cell">
                    {akte.status ? STATUS[akte.status] : "nicht berechenbar"}
                  </td>
                  <td className="kern-table__cell kern-table__cell--numeric">
                    {akte.restschuld ? formatiereBetrag(akte.restschuld) : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NeueAkte angelegt={(id) => (window.location.hash = `#/akten/${id}`)} />
    </section>
  );
}
