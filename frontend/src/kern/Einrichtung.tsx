// SPDX-License-Identifier: AGPL-3.0-or-later
// Einrichtung des Haushalts beim ersten Start: Das Bundesland bestimmt die Feiertage für
// Fristen und Verjährung (Fachkonzept Kap. 5.4).
import { useState, type FormEvent } from "react";

import { api, fehlertext } from "./api/client";
import { Meldung } from "./Meldung";

export const BUNDESLAENDER: ReadonlyArray<readonly [string, string]> = [
  ["BW", "Baden-Württemberg"],
  ["BY", "Bayern"],
  ["BE", "Berlin"],
  ["BB", "Brandenburg"],
  ["HB", "Bremen"],
  ["HH", "Hamburg"],
  ["HE", "Hessen"],
  ["MV", "Mecklenburg-Vorpommern"],
  ["NI", "Niedersachsen"],
  ["NW", "Nordrhein-Westfalen"],
  ["RP", "Rheinland-Pfalz"],
  ["SL", "Saarland"],
  ["SN", "Sachsen"],
  ["ST", "Sachsen-Anhalt"],
  ["SH", "Schleswig-Holstein"],
  ["TH", "Thüringen"],
];

export function Einrichtung({ fertig }: { fertig: () => void }) {
  const [bundesland, setBundesland] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    const { error } = await api.POST("/api/haushalt", { body: { bundesland } });
    if (error) {
      setFehler(fehlertext(error));
      return;
    }
    fertig();
  }

  return (
    <section className="kern-stack">
      <h1 className="kern-heading-large">Willkommen</h1>
      <p className="kern-body">
        Bevor es losgeht: In welchem Bundesland wohnst du? Danach richten sich die Feiertage, wenn
        bei einem Ereignis kein Gericht erfasst ist.
      </p>
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      <form onSubmit={(e) => void absenden(e)} className="kern-stack">
        <div className="kern-form-input">
          <label className="kern-label" htmlFor="bundesland">
            Bundesland
          </label>
          <div className="kern-form-input__select-wrapper">
            <select
              id="bundesland"
              className="kern-form-input__select"
              required
              value={bundesland}
              onChange={(e) => setBundesland(e.target.value)}
            >
              <option value="">Bitte wählen</option>
              {BUNDESLAENDER.map(([kuerzel, name]) => (
                <option key={kuerzel} value={kuerzel}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <button type="submit" className="kern-btn kern-btn--primary">
            <span className="kern-label">Haushalt einrichten</span>
          </button>
        </div>
      </form>
    </section>
  );
}
