// SPDX-License-Identifier: AGPL-3.0-or-later
// Seite „Lizenzen“ (Fachkonzept 11.3): Lizenz des Finanzmanagers, Lizenzhinweise der Pakete im
// Bundle der Oberfläche (beim Build geprüft und erzeugt) und der Pakete des Servers.
import { useEffect, useState } from "react";

import { api, type Schemas } from "./api/client";
import drittanbieter from "./lizenzen/drittanbieter.json";

type Hinweis = { name: string; version: string; lizenz: string; text: string };

function Pakete({ titel, pakete }: { titel: string; pakete: readonly Hinweis[] }) {
  return (
    <section className="kern-stack" aria-label={titel}>
      <h2 className="kern-heading-medium">{titel}</h2>
      <div className="kern-details-group">
        {pakete.map((p) => (
          <details className="kern-details" key={`${p.name}@${p.version}`}>
            <summary className="kern-details__header">
              <span className="kern-title">
                {p.name} {p.version} – {p.lizenz}
              </span>
            </summary>
            <div className="kern-details__body">
              <pre className="fm-lizenztext">{p.text || "Kein Lizenztext im Paket enthalten."}</pre>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

export function Lizenzen() {
  const [info, setInfo] = useState<Schemas["Info"] | null>(null);
  const [server, setServer] = useState<Schemas["Lizenz"][] | null>(null);

  useEffect(() => {
    void api.GET("/api/info").then(({ data }) => data && setInfo(data));
    void api.GET("/api/lizenzen").then(({ data }) => data && setServer(data));
  }, []);

  return (
    <article className="kern-stack">
      <h1 className="kern-heading-large">Lizenzen</h1>
      <section className="kern-stack" aria-label="Finanzmanager">
        <h2 className="kern-heading-medium">Finanzmanager</h2>
        <p className="kern-body">
          Der Finanzmanager ist freie Software unter der GNU Affero General Public License,
          Version 3 oder später ({info?.lizenz ?? "AGPL-3.0-or-later"}). Du darfst ihn nutzen,
          verändern und weitergeben. Wer eine veränderte Fassung im Netz anbietet, muss deren
          Quellcode zugänglich machen.{" "}
          <a className="kern-link" href={info?.quellcode ?? "#/"}>
            Quellcode dieser Version
          </a>
        </p>
      </section>
      <Pakete titel="Pakete der Oberfläche" pakete={drittanbieter as Hinweis[]} />
      {server === null ? (
        <p className="kern-body">Lizenzen des Servers werden geladen …</p>
      ) : (
        <Pakete titel="Pakete des Servers" pakete={server} />
      )}
    </article>
  );
}
