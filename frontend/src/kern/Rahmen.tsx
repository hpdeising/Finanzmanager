// SPDX-License-Identifier: AGPL-3.0-or-later
// Rahmen jeder Seite: Kopf mit Navigation und Fuß mit Version, Lizenz und Link auf den
// Quellcode der laufenden Version (AGPL-3.0 § 13). Dieser Link wird nicht entfernt.
import { useEffect, useState, type ReactNode } from "react";

import { api, type Schemas } from "./api/client";

export function Rahmen({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<Schemas["Info"] | null>(null);

  useEffect(() => {
    void api.GET("/api/info").then(({ data }) => {
      if (data) {
        setInfo(data);
      }
    });
  }, []);

  return (
    <>
      <header className="fm-kopf">
        <div className="kern-container">
          <nav aria-label="Hauptnavigation" className="fm-navigation">
            <a className="kern-link fm-marke" href="#/">
              Finanzmanager
            </a>
            <a className="kern-link" href="#/">
              Akten
            </a>
          </nav>
        </div>
      </header>
      <main className="kern-container fm-inhalt" id="inhalt">
        {children}
      </main>
      <footer className="kern-container fm-fuss">
        <p className="kern-body kern-body--small">
          Finanzmanager {info ? `Version ${info.version}` : ""} · Freie Software unter der
          Lizenz {info?.lizenz ?? "AGPL-3.0-or-later"} ·{" "}
          <a className="kern-link kern-link--small" href={info?.quellcode ?? "#/"}>
            Quellcode dieser Version
          </a>
        </p>
      </footer>
    </>
  );
}
