// SPDX-License-Identifier: AGPL-3.0-or-later
// Einstieg der Oberfläche. KERN bindet index.html unverändert ein (scripts/kern.mjs). Die
// Schriften des Pakets (Fira Sans, OFL-1.1) sind noch nicht eingebunden.
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
