// SPDX-License-Identifier: AGPL-3.0-or-later
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { barrieren, bildeApiNach } from "../../testhilfen";
import { Aktenliste } from "./Aktenliste";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const AKTE = {
  id: "0b6c1e9e-8a8f-4c55-9a55-1f0d6f3c2b11",
  glaeubiger_name: "Muster Inkasso",
  aktenzeichen_glaeubiger: "AZ-7",
  angelegt_am: "2026-11-21T04:00:00Z",
  status: "tituliert",
  restschuld: "1234.5",
};

describe("Aktenliste", () => {
  it("zeigt Gläubiger, Status und Restschuld als Text", async () => {
    bildeApiNach({ "/api/verbindlichkeiten/akten": [AKTE], "/api/verbindlichkeiten/glaeubiger": [] });
    render(<Aktenliste />);
    const link = await screen.findByRole("link", { name: "Muster Inkasso" });
    expect(link.getAttribute("href")).toBe(`#/akten/${AKTE.id}`);
    expect(screen.getByText("Tituliert")).toBeTruthy();
    expect(screen.getByText("1.234,50 €")).toBeTruthy();
  });

  it("ohne Akten einen Hinweis und das Formular", async () => {
    bildeApiNach({ "/api/verbindlichkeiten/akten": [], "/api/verbindlichkeiten/glaeubiger": [] });
    render(<Aktenliste />);
    expect(await screen.findByText(/Noch keine Akte/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Akte anlegen" })).toBeTruthy();
  });

  it("hat keine automatisch erkennbaren Barrieren", async () => {
    bildeApiNach({ "/api/verbindlichkeiten/akten": [AKTE], "/api/verbindlichkeiten/glaeubiger": [] });
    const { container } = render(<Aktenliste />);
    await screen.findByRole("link", { name: "Muster Inkasso" });
    expect(await barrieren(container)).toEqual([]);
  });
});
