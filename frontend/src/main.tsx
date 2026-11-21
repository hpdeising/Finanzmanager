// SPDX-License-Identifier: AGPL-3.0-or-later
// Einstieg der Oberfläche. KERN wird unverändert eingebunden (CLAUDE.md, Lizenzen); die
// Schriften des Pakets nicht, weil Fira Sans unter OFL-1.1 steht (nicht auf der Liste).
import "@kern-ux/native/dist/kern.min.css";
import "./kern/stil.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const wurzel = document.getElementById("app");
if (wurzel) {
  createRoot(wurzel).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
