// SPDX-License-Identifier: AGPL-3.0-or-later
// @vitest-environment node
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { erlaubtNachSpdx, erlaubteFamilien, lizenzangabe, SPDX_FAMILIE } from "./lizenzpruefung.mjs";

const BEISPIEL = new Set(["MIT", "BSD", "Apache-2.0", "PSF-2.0", "LGPL", "GPL-3.0", "MPL-2.0"]);
const MIT_OFL_UND_0BSD = new Set([...BEISPIEL, "OFL-1.1", "0BSD"]);

describe("erlaubteFamilien", () => {
  it("liest die Liste aus CLAUDE.md", () => {
    const text = "- Erlaubte Lizenzen für Abhängigkeiten: MIT, OLDAP-2.8, Public Domain. KERN-UX …\n";
    expect(erlaubteFamilien(text)).toEqual(new Set(["MIT", "OLDAP-2.8", "Public Domain"]));
  });

  it("ohne Liste ein Fehler", () => {
    expect(() => erlaubteFamilien("keine Liste")).toThrow(/Erlaubte Lizenzen/);
  });

  it("die Abbildung zeigt nur auf Familien aus CLAUDE.md", () => {
    const erlaubt = erlaubteFamilien(readFileSync(new URL("../../CLAUDE.md", import.meta.url), "utf8"));
    for (const familie of Object.values(SPDX_FAMILIE)) {
      expect(erlaubt.has(familie), familie).toBe(true);
    }
  });
});

describe("erlaubtNachSpdx", () => {
  it.each([
    ["MIT", true],
    ["MIT AND BSD-3-Clause", true],
    ["Apache-2.0 OR BSD-2-Clause", true],
    ["(MIT OR CC0-1.0)", true],
    ["BUSL-1.1 OR MIT", true],
    ["MIT AND BUSL-1.1", false],
    ["GPL-2.0-only", false],
    ["0BSD", false],
    ["BlueOak-1.0.0", false],
    ["CC-BY-4.0", false],
    ["keine Angabe", false],
    ["", false],
  ])("%j → %s", (ausdruck, erwartet) => {
    expect(erlaubtNachSpdx(ausdruck, BEISPIEL)).toBe(erwartet);
  });

  it.each(["0BSD", "OFL-1.1"])("%s nur, wenn die Liste es nennt (Entscheidung vom 21.11.2026)", (k) => {
    expect(erlaubtNachSpdx(k, BEISPIEL)).toBe(false);
    expect(erlaubtNachSpdx(k, MIT_OFL_UND_0BSD)).toBe(true);
  });

  it("die Liste in CLAUDE.md nennt 0BSD und OFL-1.1", () => {
    const erlaubt = erlaubteFamilien(readFileSync(new URL("../../CLAUDE.md", import.meta.url), "utf8"));
    expect(erlaubt.has("0BSD")).toBe(true);
    expect(erlaubt.has("OFL-1.1")).toBe(true);
  });

  it("EUPL-1.2 nur für KERN-UX (CLAUDE.md: KERN-UX nur unverändert)", () => {
    expect(erlaubtNachSpdx("EUPL-1.2", BEISPIEL, "@kern-ux/native")).toBe(true);
    expect(erlaubtNachSpdx("EUPL-1.2", BEISPIEL, "irgendein-paket")).toBe(false);
  });
});

describe("lizenzangabe", () => {
  it("liest license und das alte Feld licenses", () => {
    expect(lizenzangabe({ license: "MIT" })).toBe("MIT");
    expect(lizenzangabe({ licenses: [{ type: "MIT" }, { type: "Apache-2.0" }] })).toBe(
      "MIT OR Apache-2.0",
    );
    expect(lizenzangabe({})).toBe("");
  });
});
