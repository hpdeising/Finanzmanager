// SPDX-License-Identifier: AGPL-3.0-or-later
// Formulare einer Akte: Bestandteil, Ereignis, Zahlung. Beträge werden als Text gesendet.
import { useState, type FormEvent, type ReactNode } from "react";

import { api, fehlertext, type Schemas } from "../../kern/api/client";
import { betragAusEingabe } from "../../kern/geld";
import { Meldung } from "../../kern/Meldung";
import { BESTANDTEILART, EREIGNISTYP, ZINSREGELTYP } from "./texte";

type Fertig = () => void;

function Feld({ id, label, children }: { id: string; label: ReactNode; children: ReactNode }) {
  return (
    <div className="kern-form-input">
      <label className="kern-label" htmlFor={id}>
        {label}
      </label>
      {children}
    </div>
  );
}

function Auswahl<T extends string>({
  id,
  werte,
  wert,
  setWert,
}: {
  id: string;
  werte: Record<T, string>;
  wert: T;
  setWert: (wert: T) => void;
}) {
  return (
    <div className="kern-form-input__select-wrapper">
      <select
        id={id}
        className="kern-form-input__select"
        value={wert}
        onChange={(e) => setWert(e.target.value as T)}
      >
        {(Object.entries(werte) as [T, string][]).map(([schluessel, name]) => (
          <option key={schluessel} value={schluessel}>
            {name}
          </option>
        ))}
      </select>
    </div>
  );
}

function Absenden({ children }: { children: ReactNode }) {
  return (
    <div>
      <button type="submit" className="kern-btn kern-btn--primary">
        <span className="kern-label">{children}</span>
      </button>
    </div>
  );
}

const OPTIONAL = <span className="kern-label__optional">(optional)</span>;

export function BestandteilFormular({ akteId, fertig }: { akteId: string; fertig: Fertig }) {
  const [kennung, setKennung] = useState("hauptforderung");
  const [art, setArt] = useState<Schemas["Bestandteilart"]>("hauptforderung");
  const [betrag, setBetrag] = useState("");
  const [entstanden, setEntstanden] = useState("");
  const [faellig, setFaellig] = useState("");
  const [zinsregel, setZinsregel] = useState<Schemas["Zinsregeltyp"]>("keine");
  const [zinsAb, setZinsAb] = useState("");
  const [satz, setSatz] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    const text = betragAusEingabe(betrag);
    if (text === null) {
      setFehler("Der Betrag ist ungültig, etwa 1.234,56.");
      return;
    }
    const brauchtSatz = zinsregel === "fest" || zinsregel === "basiszins_plus";
    const satzText = brauchtSatz ? betragAusEingabe(satz) : null;
    if (brauchtSatz && satzText === null) {
      setFehler("Der Satz ist ungültig, etwa 5 oder 4,5.");
      return;
    }
    const zinsregeln: Schemas["ZinsregelSchema"][] =
      zinsregel === "keine"
        ? []
        : [
            {
              typ: zinsregel,
              ab: zinsAb || null,
              satz: zinsregel === "fest" ? satzText : null,
              aufschlag: zinsregel === "basiszins_plus" ? satzText : null,
            },
          ];
    const { error } = await api.POST("/api/verbindlichkeiten/akten/{akte_id}/bestandteile", {
      params: { path: { akte_id: akteId } },
      body: {
        kennung,
        art,
        betrag: text,
        entstanden_am: entstanden,
        faellig_am: faellig || null,
        zinsregeln,
      },
    });
    if (error) {
      setFehler(fehlertext(error));
      return;
    }
    setFehler(null);
    setBetrag("");
    fertig();
  }

  return (
    <form onSubmit={(e) => void absenden(e)} className="kern-stack" aria-label="Bestandteil">
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      <div className="fm-formular">
        <Feld id="b-kennung" label="Kennung">
          <input
            id="b-kennung"
            className="kern-form-input__input"
            required
            value={kennung}
            onChange={(e) => setKennung(e.target.value)}
          />
        </Feld>
        <Feld id="b-art" label="Art">
          <Auswahl id="b-art" werte={BESTANDTEILART} wert={art} setWert={setArt} />
        </Feld>
        <Feld id="b-betrag" label="Betrag in Euro">
          <input
            id="b-betrag"
            className="kern-form-input__input"
            inputMode="decimal"
            required
            value={betrag}
            onChange={(e) => setBetrag(e.target.value)}
          />
        </Feld>
        <Feld id="b-entstanden" label="Entstanden am">
          <input
            id="b-entstanden"
            type="date"
            className="kern-form-input__input"
            required
            value={entstanden}
            onChange={(e) => setEntstanden(e.target.value)}
          />
        </Feld>
        <Feld id="b-faellig" label={<>Fällig am {OPTIONAL}</>}>
          <input
            id="b-faellig"
            type="date"
            className="kern-form-input__input"
            value={faellig}
            onChange={(e) => setFaellig(e.target.value)}
          />
        </Feld>
        <Feld id="b-zinsregel" label="Zinsen">
          <Auswahl id="b-zinsregel" werte={ZINSREGELTYP} wert={zinsregel} setWert={setZinsregel} />
        </Feld>
        {zinsregel !== "keine" && (
          <Feld id="b-zins-ab" label="Zinsen ab">
            <input
              id="b-zins-ab"
              type="date"
              className="kern-form-input__input"
              required
              value={zinsAb}
              onChange={(e) => setZinsAb(e.target.value)}
            />
          </Feld>
        )}
        {(zinsregel === "fest" || zinsregel === "basiszins_plus") && (
          <Feld id="b-satz" label={zinsregel === "fest" ? "Jahreszins in Prozent" : "Aufschlag in Prozentpunkten"}>
            <input
              id="b-satz"
              className="kern-form-input__input"
              inputMode="decimal"
              required
              value={satz}
              onChange={(e) => setSatz(e.target.value)}
            />
          </Feld>
        )}
      </div>
      <Absenden>Bestandteil hinzufügen</Absenden>
    </form>
  );
}

type Erfassbar = Exclude<Schemas["Ereignistyp"], "zahlung">;
const ERFASSBAR = Object.fromEntries(
  Object.entries(EREIGNISTYP).filter(([typ]) => typ !== "zahlung"),
) as Record<Erfassbar, string>;

export function EreignisFormular({ akteId, fertig }: { akteId: string; fertig: Fertig }) {
  const [typ, setTyp] = useState<Erfassbar>("zustellung_mahnbescheid");
  const [datum, setDatum] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    const { error } = await api.POST("/api/verbindlichkeiten/akten/{akte_id}/ereignisse", {
      params: { path: { akte_id: akteId } },
      body: { typ, datum: datum || null },
    });
    if (error) {
      setFehler(fehlertext(error));
      return;
    }
    setFehler(null);
    fertig();
  }

  return (
    <form onSubmit={(e) => void absenden(e)} className="kern-stack" aria-label="Ereignis">
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      <div className="fm-formular">
        <Feld id="e-typ" label="Ereignis">
          <Auswahl id="e-typ" werte={ERFASSBAR} wert={typ} setWert={setTyp} />
        </Feld>
        <Feld id="e-datum" label={<>Datum {OPTIONAL}</>}>
          <input
            id="e-datum"
            type="date"
            className="kern-form-input__input"
            value={datum}
            onChange={(e) => setDatum(e.target.value)}
          />
        </Feld>
      </div>
      <Absenden>Ereignis erfassen</Absenden>
    </form>
  );
}

export function ZahlungFormular({ akteId, fertig }: { akteId: string; fertig: Fertig }) {
  const [datum, setDatum] = useState("");
  const [betrag, setBetrag] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    const text = betragAusEingabe(betrag);
    if (text === null) {
      setFehler("Der Betrag ist ungültig, etwa 150,00.");
      return;
    }
    const { error } = await api.POST("/api/verbindlichkeiten/akten/{akte_id}/zahlungen", {
      params: { path: { akte_id: akteId } },
      body: { datum, betrag: text },
    });
    if (error) {
      setFehler(fehlertext(error));
      return;
    }
    setFehler(null);
    setBetrag("");
    fertig();
  }

  return (
    <form onSubmit={(e) => void absenden(e)} className="kern-stack" aria-label="Zahlung">
      {fehler && <Meldung art="danger">{fehler}</Meldung>}
      <div className="fm-formular">
        <Feld id="z-datum" label="Wertstellung">
          <input
            id="z-datum"
            type="date"
            className="kern-form-input__input"
            required
            value={datum}
            onChange={(e) => setDatum(e.target.value)}
          />
        </Feld>
        <Feld id="z-betrag" label="Betrag in Euro">
          <input
            id="z-betrag"
            className="kern-form-input__input"
            inputMode="decimal"
            required
            value={betrag}
            onChange={(e) => setBetrag(e.target.value)}
          />
        </Feld>
      </div>
      <Absenden>Zahlung erfassen</Absenden>
    </form>
  );
}
