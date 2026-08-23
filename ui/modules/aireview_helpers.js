// Pure helpers for the AI Constructability Review view — no DOM, no imports,
// so they're unit-testable under plain Node (tests/js/test_aireview.js).

// Returns a themeable CSS colour (a --var) for a score band, so the gauge/marker follow the
// active appearance mode. green=Ready, amber=Minor, orange=Significant, red=Major.
export function bandHex(band) {
  return { green: 'var(--success)', amber: 'var(--warning)', orange: 'var(--chart-3)', red: 'var(--danger)' }[band] || 'var(--muted)';
}

export function kindClass(kind) {
  return { add: 'ai-add', remove: 'ai-rem', change: 'ai-chg', keep: 'ai-keep' }[kind] || '';
}

// Clamp a score to a 0–100 gauge position.
export function markerLeft(score) {
  return Math.max(0, Math.min(100, Number(score) || 0));
}

export function impactPill(impact) {
  if (impact === 'Critical') return '<span class="ai-pill ai-crit">Critical</span>';
  if (impact === 'Near-critical') return '<span class="ai-pill ai-warn">Near-critical</span>';
  return '<span class="ai-pill ai-minor">Minor</span>';
}
