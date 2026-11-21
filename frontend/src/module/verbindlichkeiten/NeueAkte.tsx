// SPDX-License-Identifier: AGPL-3.0-or-later
// Neue Akte anlegen: Gläubiger wählen oder neu anlegen, Aktenzeichen, Verbraucherdarlehen.
// Die Aktenparameter gelten mit den Voreinstellungen des Fachkonzepts (Kap. 5.1).
import { useEffect, useState, type FormEvent } from "react";

import { api, fehlertext, type Schemas } from "../../kern/api/client";
import { Meldung } from "../../kern/Meldung";

const NEU = "neu";

export function NeueAkte({ angelegt }: { angelegt: (id: string) => void }) {
  const [glaeubiger, setGlaeubiger] = useState<Schemas["GlaeubigerAusgabe"][]>([]);
  const [auswahl, setAuswahl] = useState(NEU);
  const [name, setName] = useState("");
  const [aktenzeichen, setAktenzeichen] = useState("");
  const [verbraucherdarlehen, setVerbraucherdarlehen] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void api.GET("/api/verbindlichkeiten/glaeubiger").then(({ data }) => {
      if (data) {
        setGlaeubiger(data);
      }
    });
  }, []);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    setFehler(null);
    let glaeubigerId = auswahl;
    if (auswahl === NEU) {
      const neu = await api.POST("/api/verbindlichkeiten/glaeubiger", { body: { name } });
      if (neu.error || !neu.data) {
        setFehler(fehlertext(neu.error));
        return;
      }
      glaeubigerId = neu.data.id;
    }
    const { data, error } = await api.POST("/api/verbindlichkeiten/akten", {
      body: {
        glaeubiger_id: glaeubigerId,
        aktenzeichen_glaeubiger: aktenzeichen || null,
        verbraucherdarlehen,
      },
    });
    if (error || !data) {
      setFehler(fehlertext(error));
      return;
    }
    angelegt(data.id);
  }

  return (
    <section className="kern-stack" aria-labelledby="neue-akte">
      <h2 className="kern-heading-medium" id="neue-akte">
        Neue Akte
      </h2>
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      <form onSubmit={(e) => void absenden(e)} className="fm-formular">
        <div className="kern-form-input">
          <label className="kern-label" htmlFor="glaeubiger">
            Gläubiger
          </label>
          <div className="kern-form-input__select-wrapper">
            <select
              id="glaeubiger"
              className="kern-form-input__select"
              value={auswahl}
              onChange={(e) => setAuswahl(e.target.value)}
            >
              <option value={NEU}>Neuer Gläubiger …</option>
              {glaeubiger.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {auswahl === NEU && (
          <div className="kern-form-input">
            <label className="kern-label" htmlFor="glaeubiger-name">
              Name des Gläubigers
            </label>
            <input
              id="glaeubiger-name"
              className="kern-form-input__input"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        )}
        <div className="kern-form-input">
          <label className="kern-label" htmlFor="aktenzeichen">
            Aktenzeichen des Gläubigers <span className="kern-label__optional">(optional)</span>
          </label>
          <input
            id="aktenzeichen"
            className="kern-form-input__input"
            value={aktenzeichen}
            onChange={(e) => setAktenzeichen(e.target.value)}
          />
        </div>
        <div className="kern-form-check">
          <input
            id="verbraucherdarlehen"
            type="checkbox"
            className="kern-form-check__checkbox"
            checked={verbraucherdarlehen}
            onChange={(e) => setVerbraucherdarlehen(e.target.checked)}
          />
          <label className="kern-label" htmlFor="verbraucherdarlehen">
            Verbraucherdarlehen
          </label>
        </div>
        <div>
          <button type="submit" className="kern-btn kern-btn--primary">
            <span className="kern-label">Akte anlegen</span>
          </button>
        </div>
      </form>
    </section>
  );
}
