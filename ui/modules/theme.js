// The app's on-screen appearance is the unified six-mode system (see appearance.js): Light,
// Dark, Midnight, Sepia, High-contrast, Blueprint. The same saved mode themes the app screen
// AND every report preview/PDF. On load, paint the whole app in the saved mode.
import { getSavedMode, applyAppMode } from './appearance.js';

export function initTheme() {
  applyAppMode(getSavedMode());
}
