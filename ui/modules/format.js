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

// ONE date style in every feature's result (comment 46): 03-Dec.2026 (fixed English month
// names, never the browser's locale). ISO dates are read by their digits, so no time-zone shift.
const _MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function dateText(v) {
  if (v == null || v === '') return '';
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return '';
    return `${String(v.getDate()).padStart(2, '0')}-${_MON[v.getMonth()]}.${v.getFullYear()}`;
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:$|[T\s])/.exec(String(v).trim());
  if (m && +m[2] >= 1 && +m[2] <= 12) return `${m[3]}-${_MON[+m[2] - 1]}.${m[1]}`;
  return '';
}
export function fmtDate(iso) {
  if (!iso) return '—';
  return dateText(iso) || String(iso);
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
