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

// The time scale of a printed Gantt / WBS: EVERY month written out (Jan, Feb, ...), upright; the
// months alternate between two rows when they would touch, and each year is written on its own
// row where it starts. data-r = the row (0 / 1 months, 1 / 2 years) - the Word export reads it too.
export function monthScaleHtml(minMs, maxMs, posFn) {
  const list = [];
  const t = new Date(minMs); t.setDate(1); t.setHours(0, 0, 0, 0);
  if (t.getTime() < minMs) t.setMonth(t.getMonth() + 1);
  for (; t.getTime() <= maxMs; t.setMonth(t.getMonth() + 1)) list.push(new Date(t));
  const stagger = list.length > 9;
  let html = '', lastYear = null;
  list.forEach((d, i) => {
    const left = posFn(d.getTime()).toFixed(2);
    html += `<span data-r="${stagger && i % 2 ? 1 : 0}" style="left:${left}%">${_MON[d.getMonth()]}</span>`;
    if (d.getFullYear() !== lastYear) {
      lastYear = d.getFullYear();
      if (i === 0 && d.getMonth() >= 10 && list.length > 2) return;
      html += `<span class="yr" data-r="${stagger ? 2 : 1}" style="left:${left}%">${lastYear}</span>`;
    }
  });
  return html;
}
