// SPDX-License-Identifier: AGPL-3.0-or-later
// KERN-UX unverändert ausliefern (CLAUDE.md, Lizenzen): Stylesheet, Lizenztext und die Schrift
// Fira Sans werden Byte für Byte nach public/kern/ kopiert. Vite gibt public/ ohne Verarbeitung
// ins Bundle; über den normalen CSS-Weg würde der Build die Dateien neu schreiben, also
// verändern. Von den Schriftdateien kommen nur die, auf die fira-sans.css verweist. Neben ihnen
// liegt der Lizenztext der Schrift (OFL-1.1), den das Paket nicht mitliefert
// (lizenzen/fira-sans/HERKUNFT.md).
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const QUELLE = join(FRONTEND, "node_modules", "@kern-ux", "native");
const ZIEL = join(FRONTEND, "public", "kern");
const SCHRIFT_CSS = join(QUELLE, "dist", "fonts", "fira-sans.css");

/** Schriftdateien, auf die das Stylesheet der Schrift verweist, z. B. fira-sans/FiraSans-Bold.woff2. */
function schriftdateien(css) {
  return [...new Set(css.match(/fira-sans\/[A-Za-z0-9-]+\.woff2/g) ?? [])].sort();
}

mkdirSync(join(ZIEL, "fonts", "fira-sans"), { recursive: true });
copyFileSync(join(QUELLE, "dist", "kern.min.css"), join(ZIEL, "kern.min.css"));
copyFileSync(join(QUELLE, "LICENSE.md"), join(ZIEL, "LICENSE.md"));
copyFileSync(SCHRIFT_CSS, join(ZIEL, "fonts", "fira-sans.css"));
const dateien = schriftdateien(readFileSync(SCHRIFT_CSS, "utf8"));
for (const datei of dateien) {
  copyFileSync(join(QUELLE, "dist", "fonts", datei), join(ZIEL, "fonts", datei));
}
copyFileSync(
  join(FRONTEND, "lizenzen", "fira-sans", "OFL.txt"),
  join(ZIEL, "fonts", "fira-sans", "OFL.txt"),
);
process.stdout.write(`KERN-UX unverändert nach public/kern/ kopiert (${dateien.length} Schriftdateien).\n`);
