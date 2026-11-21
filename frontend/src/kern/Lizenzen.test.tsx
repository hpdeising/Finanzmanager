// SPDX-License-Identifier: AGPL-3.0-or-later
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { barrieren, bildeApiNach } from "../testhilfen";
import { Lizenzen } from "./Lizenzen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ANTWORTEN = {
  "/api/info": { version: "0.0.0", lizenz: "AGPL-3.0-or-later", quellcode: "https://example.org/q" },
  "/api/lizenzen": [{ name: "fastapi", version: "1.0.0", lizenz: "MIT", text: "MIT License …" }],
};

describe("Lizenzen", () => {
  it("nennt die eigene Lizenz, die Pakete der Oberfläche und des Servers", async () => {
    bildeApiNach(ANTWORTEN);
    render(<Lizenzen />);
    expect(await screen.findByText("fastapi 1.0.0 – MIT")).toBeTruthy();
    expect(screen.getByText(/react \d+\.\d+\.\d+ – MIT/)).toBeTruthy();
    expect(screen.getByText(/@kern-ux\/native .* – EUPL-1.2/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Quellcode dieser Version" })).toBeTruthy();
  });

  it("hat keine automatisch erkennbaren Barrieren", async () => {
    bildeApiNach(ANTWORTEN);
    const { container } = render(<Lizenzen />);
    await screen.findByText("fastapi 1.0.0 – MIT");
    expect(await barrieren(container)).toEqual([]);
  });
});
