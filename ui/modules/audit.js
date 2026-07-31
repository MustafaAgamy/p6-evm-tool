// ── Pure helpers (unit-tested in tests/js/test_audit.js) ──────────────────

export function filterFindings(findings, { severity, check, wbs, query } = {}) {
  const q = (query || '').trim().toLowerCase();
  return findings.filter(f => {
    if (severity && f.severity !== severity) return false;
    if (check && f.check_name !== check) return false;
    if (wbs && !(f.wbs_path || '').toLowerCase().includes(wbs.toLowerCase())) return false;
    if (q) {
      const hay = `${f.activity_id || ''} ${f.activity_name || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function severityClass(sev) {
  return { Critical: 't-crit', High: 't-high', Medium: 't-med', Low: 't-low' }[sev] || 't-low';
}

export function scoreColor(score) {
  if (score >= 85) return 'color-green';
  if (score >= 60) return 'color-amber';
  return 'color-red';
}

export function gaugeDashoffset(score, circumference) {
  const s = Math.max(0, Math.min(100, score || 0));
  return circumference * (1 - s / 100);
}

export function uniqueValues(findings, key) {
  return [...new Set(findings.map(f => f[key]).filter(Boolean))].sort();
}
