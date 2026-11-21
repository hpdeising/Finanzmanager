// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { betragAusEingabe, formatiereBetrag } from "./geld";

describe("formatiereBetrag", () => {
  it.each([
    ["1234.5", "1.234,50 €"],
    ["0.00", "0,00 €"],
    ["1000000.00", "1.000.000,00 €"],
    ["-35.66", "−35,66 €"],
    ["12.3456", "12,3456 €"],
    ["7", "7,00 €"],
  ])("%s → %s", (text, erwartet) => {
    expect(formatiereBetrag(text)).toBe(erwartet);
  });
});

describe("betragAusEingabe", () => {
  it.each([
    ["1.234,56", "1234.56"],
    ["1234,56", "1234.56"],
    ["150", "150"],
    [" 150,00 € ", "150.00"],
    ["0,5", "0.5"],
  ])("%s → %s", (eingabe, erwartet) => {
    expect(betragAusEingabe(eingabe)).toBe(erwartet);
  });

  it.each(["", "abc", "1,2,3", "1.23", "-5", "1,23456", "12.34.56"])("lehnt %j ab", (eingabe) => {
    expect(betragAusEingabe(eingabe)).toBeNull();
  });
});
