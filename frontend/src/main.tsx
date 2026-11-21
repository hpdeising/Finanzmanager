// SPDX-License-Identifier: AGPL-3.0-or-later
// Einstieg der Oberfläche. KERN bindet index.html unverändert ein (scripts/kern.mjs); die
// Schriften des Pakets nicht, weil Fira Sans unter OFL-1.1 steht (nicht auf der Liste).
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
