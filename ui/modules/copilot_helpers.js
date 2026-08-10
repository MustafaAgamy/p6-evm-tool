// Pure helpers for the AI Copilot tab — no DOM, unit-tested in tests/js/test_copilot.js.

// Find the activity whose Id matches the typed text exactly (case-insensitive, trimmed).
// Used by the type-ahead Activity-ID search so the planner can jump straight to an activity.
export function matchActivity(activities, value) {
  const v = (value || '').trim().toLowerCase();
  if (!v || !activities) return null;
  return activities.find(a => (a.id || '').toLowerCase() === v) || null;
}
