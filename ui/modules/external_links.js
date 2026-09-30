// External links — every link to a web page opens in the planner's DEFAULT BROWSER, never
// inside the app window.
//
// Why: the app is a WebView. A plain <a href="https://…"> without target="_blank" navigates
// the whole window away from the tool — there is no Back button, so the planner is stranded
// until they close and reopen the app. (The map's "Leaflet" attribution link did exactly
// that.) A target="_blank" link is handed to the browser by pywebview, but with no allow-list.
//
// So ONE window-level click listener (CAPTURE phase — Leaflet's attribution control stops
// click propagation, so a bubbling listener would never see it) intercepts every http(s)
// link that is not the local server and routes it through the packaged app's
// js_api.open_external(url) — the https allow-list in utils.EXTERNAL_LINK_HOSTS (app.py).
// If the app refuses or the browser can't start, a visible in-page note shows the address
// to copy (WebView2 alert/confirm are no-ops). In a plain browser (dev harness) the link
// opens in a new tab instead.

export const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

/** True for an http(s) link to somewhere other than the app's own local server. */
export function isExternalHref(href, base) {
  if (!href || typeof href !== 'string') return false;
  let u;
  try { u = new URL(href, base || 'http://localhost/'); } catch { return false; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
  return !LOCAL_HOSTS.has((u.hostname || '').toLowerCase());
}

let _noteTimer = null;

/** A small in-page note (never alert(): it is a no-op in WebView2). */
export function showLinkNote(text, doc = (typeof document !== 'undefined' ? document : null)) {
  if (!doc || !doc.body) return null;
  let el = doc.getElementById('ext-link-note');
  if (!el) {
    el = doc.createElement('div');
    el.id = 'ext-link-note';
    el.setAttribute('role', 'status');
    el.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:3000;'
      + 'max-width:min(640px,92vw);padding:11px 16px;border-radius:10px;font-size:13px;line-height:1.45;'
      + 'background:var(--panel,#1f2937);color:var(--text,#f9fafb);border:1px solid var(--border,#374151);'
      + 'box-shadow:0 8px 28px rgba(0,0,0,.28);word-break:break-all;user-select:text;';
    doc.body.appendChild(el);
  }
  el.textContent = text;
  el.hidden = false;
  if (_noteTimer) clearTimeout(_noteTimer);
  _noteTimer = setTimeout(() => { el.hidden = true; }, 9000);
  return el;
}

/**
 * Open `url` in the default browser. Resolves true when handed over.
 *   env.api  — the pywebview js_api (window.pywebview.api) in the packaged app
 *   env.win  — the window (dev/browser fallback: a new tab)
 *   env.note — how to tell the planner it failed (default: showLinkNote)
 */
export async function openExternal(url, env = {}) {
  const win = env.win || (typeof window !== 'undefined' ? window : null);
  const api = env.api !== undefined ? env.api : (win && win.pywebview && win.pywebview.api);
  const note = env.note || showLinkNote;
  const fail = () => {
    note(`This link could not be opened in your browser from the app. Copy the address into your browser: ${url}`);
    return false;
  };
  if (api && typeof api.open_external === 'function') {
    try {
      const ok = await api.open_external(url);
      return ok ? true : fail();
    } catch {
      return fail();
    }
  }
  try {
    const w = win && typeof win.open === 'function' ? win.open(url, '_blank', 'noopener') : null;
    // window.open with 'noopener' returns null even on success — only a thrown error is a failure.
    void w;
    return true;
  } catch {
    return fail();
  }
}

/** The click decision, separated for tests: the external href to open, or null. */
export function externalLinkTarget(ev, base) {
  if (!ev || ev.defaultPrevented) return null;
  if (typeof ev.button === 'number' && ev.button !== 0) return null;
  const t = ev.target;
  const a = t && typeof t.closest === 'function' ? t.closest('a[href]') : null;
  if (!a) return null;
  const raw = a.getAttribute('href');
  if (!isExternalHref(raw, base)) return null;
  try { return new URL(raw, base || 'http://localhost/').href; } catch { return null; }
}

let _installed = false;

/** Install the one window-level interceptor (idempotent). */
export function installExternalLinks(win = (typeof window !== 'undefined' ? window : null)) {
  if (!win || _installed) return false;
  _installed = true;
  const handler = (ev) => {
    const href = externalLinkTarget(ev, win.location && win.location.href);
    if (!href) return;
    ev.preventDefault();
    ev.stopPropagation();          // the link's own handler must not open it a second time
    openExternal(href, { win });
  };
  win.addEventListener('click', handler, true);
  // Middle-click / wheel-click on a link would ask the WebView for a new window.
  win.addEventListener('auxclick', (ev) => {
    if (ev.button !== 1) return;
    const href = externalLinkTarget({ target: ev.target, button: 0, defaultPrevented: ev.defaultPrevented },
      win.location && win.location.href);
    if (!href) return;
    ev.preventDefault();
    ev.stopPropagation();
    openExternal(href, { win });
  }, true);
  return true;
}
