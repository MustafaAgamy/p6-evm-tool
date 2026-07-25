export function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function fmtEGP(n) {
  if (n == null) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return `EGP ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `EGP ${(n / 1e6).toFixed(1)}M`;
  return `EGP ${Math.round(n).toLocaleString()}`;
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function kpiColor(val, type) {
  if (val == null) return 'color-neutral';
  if (type === 'delay') return val > 0 ? 'color-red' : 'color-green';
  if (type === 'index') {
    if (val < 0.85) return 'color-red';
    if (val < 1.0)  return 'color-amber';
    return 'color-green';
  }
  return 'color-neutral';
}
