// SPDX-License-Identifier: AGPL-3.0-or-later
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { barrieren, bildeApiNach } from "../../testhilfen";
import { Akte } from "./Akte";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ID = "0b6c1e9e-8a8f-4c55-9a55-1f0d6f3c2b11";
const DETAIL = {
  id: ID,
  stichtag: "2025-06-30",
  glaeubiger_id: "5d0f4a3e-1c2b-4a9d-8e7f-6a5b4c3d2e1f",
  glaeubiger_name: "Muster Inkasso",
  aktenzeichen_glaeubiger: "AZ-7",
  verbraucherdarlehen: false,
  parameter: {
    anrechnung: "bgb_367",
    reihenfolge: null,
    tageszaehlung: "act_365",
    zinsbeginn: "genannter_tag",
    zahltag: "alter_betrag",
    teilung: "kalender",
    teilungstage: [],
  },
  bestandteile: [
    {
      kennung: "hauptforderung",
      art: "hauptforderung",
      betrag: "1000.00",
      entstanden_am: "2024-01-15",
      faellig_am: null,
      kenntnis_am: null,
      zinsregeln: [],
    },
  ],
  ereignisse: [
    {
      id: "9a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
      typ: "zahlung",
      datum: "2025-02-03",
      versaeumnisurteil: false,
      bekanntgabe_am: null,
      gericht_land: null,
      betrag: "150.00",
      storniert: false,
    },
  ],
  berechnung: {
    hauptforderung: "850.00",
    zinsen: "12.34",
    kosten: "0.00",
    restschuld: "862.34",
    ueberzahlung: "0.00",
    abschnitte: [],
  },
  fristen: [
    {
      name: "Widerspruch gegen Mahnbescheid",
      norm: "§ 692 Abs. 1 Nr. 3, § 694 Abs. 1 ZPO",
      ausloeser: "zustellung_mahnbescheid",
      ende: "2025-03-17",
      art: "prozessual",
      warnstufen: [],
      hinweis: null,
    },
  ],
  verjaehrung: [],
  verjaehrung_pflichthinweis: "Verjährung tritt nicht von selbst ein.",
  status: {
    status: "mahnverfahren",
    merkmale: [],
    aufgaben: [],
    ausgeglichen_am: null,
    hinweise: [],
    warnungen: [],
  },
  hinweise: [],
};

describe("Akte", () => {
  it("zeigt Restschuld, Status, Fristen und Zahlungen", async () => {
    bildeApiNach({ [`/api/verbindlichkeiten/akten/${ID}`]: DETAIL });
    render(<Akte id={ID} />);
    expect(await screen.findByRole("heading", { name: "Muster Inkasso" })).toBeTruthy();
    expect(screen.getByText("862,34 €")).toBeTruthy();
    expect(screen.getByText("Mahnverfahren")).toBeTruthy();
    expect(screen.getByText("17.03.2025")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stornieren" })).toBeTruthy();
    expect(screen.getByText("Verjährung tritt nicht von selbst ein.")).toBeTruthy();
  });

  it("hat keine automatisch erkennbaren Barrieren", async () => {
    bildeApiNach({ [`/api/verbindlichkeiten/akten/${ID}`]: DETAIL });
    const { container } = render(<Akte id={ID} />);
    await screen.findByRole("heading", { name: "Muster Inkasso" });
    expect(await barrieren(container)).toEqual([]);
  });
});
