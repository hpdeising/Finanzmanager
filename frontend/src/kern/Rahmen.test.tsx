// SPDX-License-Identifier: AGPL-3.0-or-later
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { barrieren, bildeApiNach } from "../testhilfen";
import { Rahmen } from "./Rahmen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Rahmen", () => {
  it("verlinkt auf den Quellcode der laufenden Version (AGPL-3.0 § 13)", async () => {
    bildeApiNach({
      "/api/info": {
        version: "0.0.0",
        lizenz: "AGPL-3.0-or-later",
        quellcode: "https://example.org/finanzmanager",
      },
    });
    render(<Rahmen>Inhalt</Rahmen>);
    const link = await screen.findByRole("link", { name: "Quellcode dieser Version" });
    await vi.waitFor(() =>
      expect(link.getAttribute("href")).toBe("https://example.org/finanzmanager"),
    );
    expect(screen.getByText(/AGPL-3.0-or-later/)).toBeTruthy();
  });

  it("hat keine automatisch erkennbaren Barrieren", async () => {
    bildeApiNach({});
    const { container } = render(<Rahmen>Inhalt</Rahmen>);
    expect(await barrieren(container)).toEqual([]);
  });
});
