// SPDX-License-Identifier: AGPL-3.0-or-later
// KERN-UX unverändert ausliefern (CLAUDE.md, Lizenzen): Stylesheet und Lizenztext werden Byte
// für Byte nach public/kern/ kopiert. Vite gibt public/ ohne Verarbeitung ins Bundle; über den
// normalen CSS-Weg würde der Build das Stylesheet neu minifizieren, also verändern.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const QUELLE = join(FRONTEND, "node_modules", "@kern-ux", "native");
const ZIEL = join(FRONTEND, "public", "kern");

mkdirSync(ZIEL, { recursive: true });
copyFileSync(join(QUELLE, "dist", "kern.min.css"), join(ZIEL, "kern.min.css"));
copyFileSync(join(QUELLE, "LICENSE.md"), join(ZIEL, "LICENSE.md"));
process.stdout.write("KERN-UX unverändert nach public/kern/ kopiert.\n");
