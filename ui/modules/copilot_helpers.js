// Pure helpers for the AI Copilot tab — no DOM, unit-tested in tests/js/test_copilot.js.

// Resolve what the planner typed or picked to a single activity, so they can search by
// Activity ID OR by name. The type-ahead list offers "ID — Name" entries; this accepts a
// bare Activity ID (exact, case-insensitive, trimmed) or a full "ID — Name" pick. Returns
// the activity, or null when nothing matches exactly yet (e.g. a half-typed name).
export function resolveActivity(activities, value) {
  const raw = (value || '').trim();
  if (!raw || !activities) return null;
  const idPart = raw.split(' — ')[0].trim().toLowerCase();
  const whole = raw.toLowerCase();
  return activities.find(a => (a.id || '').toLowerCase() === idPart)
      || activities.find(a => `${a.id} — ${a.name}`.toLowerCase() === whole)
      || null;
}
