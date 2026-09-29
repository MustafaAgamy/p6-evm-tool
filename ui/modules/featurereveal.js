// Feature Run presentation — the branded "Loading → 100%" card every feature's Run plays
// (same motion family as the startup splash, boot.js). Self-contained (injects its own CSS
// once). ONE shared mechanism for every feature:
//
//   revealAndRun(host, title, work, opts?)                   ← THE default for every Run
//   playFeatureReveal(host, { title, onDone?, gate? })       (compatibility wrapper)
//
// Owner rule (comment 36, "no gap after Run"): the results are on screen the moment the bar
// reaches 100% — never a wait after 100%. So the bar follows REAL stages, not a fixed timer:
//   Analysing → Calculating (a request to the local server is in flight: an ESTIMATED creep
//   that can never reach 100) → Results received → Rendering results → 100% only in the
//   frame AFTER the results were rendered AND painted underneath the opaque overlay → the
//   overlay starts fading in that same frame (no hold).
// Requests are observed through a thin tap on window.fetch that only listens while a reveal
// is open, so every feature gets honest "sent / received" stages with no extra code.
// The overlay mounts on the feature's view panel (never on the element the work replaces),
// so a feature that writes a placeholder into its body cannot destroy the presentation.

// ── Pure stage model (no DOM — unit-tested in tests/js/test_featurereveal.js) ─────────────

export const REVEAL_TIMING = Object.freeze({
  MIN_SHOW_MS: 800,        // an instant result still gets a short, smooth fill (0 → 100 over ≥ 0.8 s)
  FINAL_MS: 120,           // once the results are painted, the bar closes the rest within this
  TAU_MS: 5000,            // time constant of the estimated creep while the work is running
  WAIT_CAP: 94,            // highest value while anything is still running (asymptote — never reached)
  RECEIVED_PCT: 90,        // every response is in; the feature is building its view
  RENDER_PCT: 97,          // the work finished (results in the DOM), waiting for their first paint
  SLOW_MS: 6000,           // after this the label says "Still calculating · N s"
});

export const REVEAL_STAGES = Object.freeze(['analysing', 'computing', 'received', 'rendering', 'painted']);

const LABELS = {
  analysing: 'Analysing',
  computing: 'Calculating',
  received:  'Results received',
  rendering: 'Rendering results',
  painted:   'Ready',
};

// A reveal's progress model. Feed it the real events (work started, request sent / done,
// work settled) and call frame(now) once per animation frame; it returns what to paint.
// Invariants (tested): the displayed value never goes down; the label never reads 100%
// until frame() returns reveal:true, which only happens once the work has settled AND a
// frame has been painted since (framesSinceSettle ≥ 2); while anything is still running the
// value stays below WAIT_CAP.
export function createRevealModel(opts) {
  opts = opts || {};
  const T = Object.assign({}, REVEAL_TIMING, opts.timing || {});
  if (opts.reduce) { T.MIN_SHOW_MS = 0; T.FINAL_MS = 0; }   // reduced motion: jump to each stage
  const s = { t0: null, last: null, display: 0, startedAt: null, inflight: 0, sent: 0,
              settledAt: null, framesSinceSettle: 0, finalRate: null, revealed: false,
              label: null,       // the feature's own name for what it is doing now (revealStage)
              band: null };      // the server's real step: its share of the bar (revealBand)

  function stage() {
    if (s.settledAt != null) return s.framesSinceSettle >= 2 ? 'painted' : 'rendering';
    if (s.inflight > 0) return 'computing';
    if (s.sent > 0) return 'received';
    return 'analysing';
  }
  function target(st, now) {
    if (st === 'painted') return 100;
    if (st === 'rendering') return T.RENDER_PCT;
    if (s.startedAt == null) return 3;
    const waited = Math.max(0, now - s.startedAt);
    let creep = 6 + (T.WAIT_CAP - 6) * (1 - Math.exp(-waited / T.TAU_MS));
    if (s.band) {
      // The server named its step: move through THAT step's share of the bar (reading each
      // file, then comparing) — an estimated creep inside the band that never passes its end.
      const b = s.band, inBand = 1 - Math.exp(-Math.max(0, now - b.t) / b.tau);
      creep = 6 + (T.WAIT_CAP - 6) * Math.min(1, Math.max(0, b.from + (b.to - b.from) * inBand));
    }
    return st === 'received' ? Math.max(T.RECEIVED_PCT, creep) : creep;
  }
  function frame(now) {
    if (s.t0 == null) { s.t0 = now; s.last = now; }
    const dt = Math.max(0, now - s.last); s.last = now;
    if (s.settledAt != null) s.framesSinceSettle++;
    const st = stage();
    const tgt = target(st, now);
    let next;
    if (T.MIN_SHOW_MS <= 0) {
      next = tgt;
    } else {
      const base = 100 / T.MIN_SHOW_MS;                         // % per ms
      let rate = base;
      if (st === 'painted') {
        if (s.finalRate == null) s.finalRate = T.FINAL_MS > 0 ? Math.max(base, (100 - s.display) / T.FINAL_MS) : Infinity;
        rate = s.finalRate;
      }
      const ceiling = 100 * (now - s.t0) / T.MIN_SHOW_MS;       // an instant result still animates
      next = Math.min(tgt, s.display + rate * dt, ceiling);
    }
    s.display = Math.max(s.display, Math.min(100, next));
    let reveal = false;
    if (st === 'painted' && s.display >= 99.95) { s.display = 100; reveal = true; s.revealed = true; }
    const pct = reveal ? 100 : Math.min(99, Math.floor(s.display));
    // The feature's own stage name (revealStage) wins while its work is still running; the
    // closing stages ("Rendering results" → "Ready") are always the shared ones.
    const own = (st === 'analysing' || st === 'computing' || st === 'received') ? s.label : null;
    let label = own || LABELS[st];
    if ((st === 'computing' || st === 'analysing') && s.startedAt != null && now - s.startedAt >= T.SLOW_MS) {
      const secs = Math.round((now - s.startedAt) / 1000) + ' s';
      label = own ? own + ' · ' + secs : 'Still calculating · ' + secs;
    }
    return { stage: st, display: s.display, pct, label, reveal };
  }
  return {
    workStarted(now) { if (s.startedAt == null) s.startedAt = now; },
    requestSent() { s.inflight++; s.sent++; },
    // When the last request answers, the feature's "…ing" label is stale: fall back to
    // "Results received" unless the feature names its next stage (revealStage again).
    requestDone() { if (s.inflight > 0) s.inflight--; if (s.inflight === 0) s.label = null; },
    setLabel(label) { s.label = label ? String(label) : null; },
    // The server's real step as a share of the calculation (0..1) and its estimated seconds.
    setBand(from, to, estS, now) {
      const a = Math.max(0, Math.min(1, +from || 0)), b = Math.max(a, Math.min(1, +to || 0));
      s.band = { from: a, to: b, t: now, tau: Math.max(300, (+estS || 0) * 1000 / 2.5) };
    },
    settled(now) { if (s.settledAt == null) s.settledAt = now; },
    frame,
    stage,
    get revealed() { return s.revealed; },
    get inflight() { return s.inflight; },
  };
}

// ── Request tap: which local-server requests are in flight while a reveal is open ─────────
// Wraps target.fetch ONCE. The wrapper returns the ORIGINAL promise unchanged (callers see
// exactly the same behaviour); it only notifies the reveals that were open when the
// request was sent. Only /api/ calls count (static files, fonts, etc. are ignored).
export const REVEAL_WATCHERS = new Set();
const TAPPED = typeof WeakSet === 'function' ? new WeakSet() : null;

function isApiRequest(input) {
  try {
    const u = typeof input === 'string' ? input : ((input && input.url) || String(input));
    return /\/api\//.test(u) && !/\/api\/run\/stage/.test(u);   // stage polls are not work
  } catch (e) { return false; }
}

export function installRequestTap(target) {
  if (!target || typeof target.fetch !== 'function') return false;
  if (TAPPED && TAPPED.has(target)) return true;
  const orig = target.fetch;
  target.fetch = function (input, init) {
    const p = orig.apply(target, arguments);
    if (REVEAL_WATCHERS.size && isApiRequest(input)) {
      const watchers = Array.from(REVEAL_WATCHERS);
      watchers.forEach(w => { try { w.requestSent(); } catch (e) {} });
      const done = () => watchers.forEach(w => { try { w.requestDone(); } catch (e) {} });
      if (p && typeof p.then === 'function') p.then(done, done); else done();
    }
    return p;
  };
  if (TAPPED) TAPPED.add(target);
  return true;
}

// A feature names the REAL stage it is in ("Downloading weather history", "Comparing Rev.00
// with Rev.01", …) and the open Run bar shows it (with the elapsed seconds on a long wait).
// Call it inside the `work` of revealAndRun, right before each step. No reveal open → no-op.
export function revealStage(label) {
  REVEAL_WATCHERS.forEach(w => { try { if (w.setLabel) w.setLabel(label); } catch (e) {} });
}

// The server's real step as a share of the bar (from..to of the calculation, 0..1).
export function revealBand(from, to, estS) {
  const now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  REVEAL_WATCHERS.forEach(w => { try { if (w.setBand) w.setBand(from, to, estS, now); } catch (e) {} });
}

// A long server Run (reading two or three whole schedules, then comparing) reports the step
// it is REALLY on (server.py _RunStages). Send `id` as `run_id` with the request, and call
// stop() when it settles; meanwhile the open Run bar shows the server's step ("Reading
// Rev.01 — <file>") and moves through that step's share of the bar.
export function followRunStages(port, opts) {
  const id = 'run-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  const every = (opts && opts.every) || 400;
  let stopped = false, timer = null, lastKey = null;
  const tick = () => {
    if (stopped) return;
    Promise.resolve()
      .then(() => fetch(`http://localhost:${port}/api/run/stage?id=${encodeURIComponent(id)}`))
      .then(r => r.json())
      .then(d => {
        const st = d && d.stage;
        if (stopped || !st || !st.label) return;
        const key = st.step + '|' + st.label;
        if (key === lastKey) return;
        lastKey = key;
        revealBand(st.from, st.to, st.est_s);
        revealStage(st.label);
      })
      .catch(() => {})
      .then(() => { if (!stopped) timer = setTimeout(tick, every); });
  };
  timer = setTimeout(tick, Math.min(every, 150));
  return { id, stop() { stopped = true; clearTimeout(timer); } };
}

// ── DOM presentation ───────────────────────────────────────────────────────────────────

let injected = false;
const MARK = 'M4 19V5M4 15l5-5 4 3 7-8';
const MOUNT_MIN_H = 360;                       // room for the card while the panel is still empty
const SETTLE_FALLBACK_MS = 1500;               // hidden window (rAF paused): reveal anyway once settled
const MAX_WAIT_MS = 15 * 60 * 1000;            // a request that never answers: stop after 15 min

function injectCss() {
  if (injected) return; injected = true;
  const css = `
  /* Opaque from the first frame (mode-aware) so the results rendered UNDERNEATH stay hidden
     until the bar reads 100%. In THAT frame the backdrop drops at once (it is not in the
     transition list), so the results are on screen with the 100%; only the card fades
     (≤ 0.1 s) and it never blocks them (pointer-events off at once). RUNUX-14. */
  .fr-ov{position:absolute; inset:0; z-index:60; display:block; opacity:1;
    background:var(--bg); transition:opacity .1s ease;
    font-family:"Segoe UI",system-ui,-apple-system,sans-serif;}
  .fr-ov.out{opacity:0; pointer-events:none; background:transparent;}
  /* Anchored near the top and sticky: results growing underneath can never move the card. */
  .fr-card{position:sticky; top:28px; margin:56px auto 24px; width:min(400px,86%); background:#fff;
    border:1px solid #e2e8f0; border-radius:16px; box-shadow:0 24px 60px -24px rgba(15,23,42,.4);
    padding:20px 22px 18px; animation:fr-pop .16s ease-out both;}
  @keyframes fr-pop{from{opacity:0; transform:translateY(6px) scale(.985);} to{opacity:1; transform:none;}}
  .fr-hd{display:flex; align-items:center; gap:13px; margin-bottom:15px;}
  .fr-ic{width:44px; height:44px; flex:none; border-radius:12px; display:grid; place-items:center;
    background:linear-gradient(135deg,rgba(246,167,35,.18),rgba(37,99,235,.16)); }
  .fr-ic svg{width:24px; height:24px;}
  .fr-eb{font:700 9.5px/1 Archivo,system-ui,sans-serif; letter-spacing:.18em; text-transform:uppercase; color:#2563eb;}
  .fr-ti{font:800 17px/1.15 Archivo,system-ui,sans-serif; color:#1e293b; margin-top:3px;}
  .fr-hd > div{min-width:0;}
  /* A long step name ("Reading Rev.01 — <file> · 12 s") stays on one line: the card never jumps. */
  .fr-st{font-size:12px; color:#64748b; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
  .fr-viz{width:100%; height:74px; display:block; margin:4px 0 13px;}
  .fr-tr{position:relative; height:4px; border-radius:4px; background:#e8edf5; overflow:hidden;}
  .fr-bf{height:100%; width:0%; border-radius:4px; background:linear-gradient(90deg,#f6a723,#2563eb);}
  /* Compositor-driven shimmer: keeps moving even while the page is busy building the results. */
  .fr-tr::after{content:""; position:absolute; top:0; bottom:0; left:0; width:28%;
    background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.75),rgba(255,255,255,0));
    animation:fr-shim 1.15s linear infinite; will-change:transform;}
  @keyframes fr-shim{from{transform:translateX(-110%);} to{transform:translateX(400%);}}
  .fr-pc{display:flex; justify-content:space-between; gap:10px; margin-top:7px; font:600 10.5px/1 "Segoe UI",system-ui;
    letter-spacing:.06em; text-transform:uppercase; color:#94a3b8;}
  .fr-pc b{color:#1e293b; font-variant-numeric:tabular-nums; font-family:Archivo,system-ui,sans-serif;}
  .fr-stt2{min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
  @media (prefers-reduced-motion: reduce){ .fr-card{animation:none;} .fr-tr::after{display:none;} .fr-ov{transition:none;} }`;
  const s = document.createElement('style'); s.id = 'fr-reveal-style'; s.textContent = css; document.head.appendChild(s);
}

const clamp = (x, a, b) => { a = a == null ? 0 : a; b = b == null ? 1 : b; return x < a ? a : x > b ? b : x; };
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3);
const nowMs = () => (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();

// The element the overlay lives on: the feature's view panel when there is one (a feature's
// work may replace its body — including the host's content — but never the panel itself).
function mountFor(host) {
  return (host && host.closest && host.closest('.view-panel')) || host;
}

function buildOverlay(title, iconPath) {
  const ov = document.createElement('div');
  ov.className = 'fr-ov';
  ov.setAttribute('role', 'status');
  ov.setAttribute('aria-live', 'polite');
  const N = 11, W = 360, rowY = [14, 34, 54];
  let bars = '';
  for (let i = 0; i < N; i++) {
    const row = i % 3, x = 20 + (i * 31) % (W - 90), w = 40 + ((i * 37) % 60), crit = (i % 4 === 0);
    bars += `<rect class="frb" data-x="${x}" data-w="${w}" data-crit="${crit ? 1 : 0}" x="${x}" y="${rowY[row]}" height="9" rx="3" fill="#c2ccdd" opacity="0"/>`;
  }
  ov.innerHTML =
    `<div class="fr-card">
      <div class="fr-hd">
        <span class="fr-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${iconPath}"/></svg></span>
        <div><div class="fr-eb"></div><div class="fr-ti"></div><div class="fr-st"><span class="fr-stt">${LABELS.analysing}</span>…</div></div>
      </div>
      <svg class="fr-viz" viewBox="0 0 ${W} 74" preserveAspectRatio="none">
        <defs><linearGradient id="frscan" x1="0" x2="1"><stop offset="0" stop-color="#2563eb" stop-opacity="0"/><stop offset="1" stop-color="#2563eb" stop-opacity=".22"/></linearGradient></defs>
        <path class="frcp" d="M12 60 L120 50 L210 40 L300 22 L348 14" fill="none" stroke="#5b9bff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" pathLength="100" opacity="0"/>
        <g class="frbars">${bars}</g>
        <rect class="frscanband" x="0" y="0" width="46" height="74" fill="url(#frscan)" opacity="0"/>
        <line class="frscanline" x1="0" y1="0" x2="0" y2="74" stroke="#2563eb" stroke-width="2" opacity="0"/>
      </svg>
      <div class="fr-tr"><div class="fr-bf"></div></div>
      <div class="fr-pc"><span class="fr-stt2">${LABELS.analysing}</span><b class="fr-pct">0%</b></div>
    </div>`;
  ov.querySelector('.fr-eb').textContent = window.__APP_NAME__ || 'Controlyx';   // brand from server.py
  ov.querySelector('.fr-ti').textContent = title;                                  // text, never markup
  return ov;
}

function makePainter(ov) {
  const W = 360;
  const barEls = [].slice.call(ov.querySelectorAll('.frb'));
  const cp = ov.querySelector('.frcp'), band = ov.querySelector('.frscanband'), line = ov.querySelector('.frscanline'),
        bf = ov.querySelector('.fr-bf'), pct = ov.querySelector('.fr-pct'), st1 = ov.querySelector('.fr-stt'), st2 = ov.querySelector('.fr-stt2');
  let lastPct = null, lastLabel = null;
  return function paint(f) {
    const t = clamp(f.display / 100, 0, 1);
    const scanX = t * W;
    band.setAttribute('x', (scanX - 46).toFixed(1)); band.setAttribute('opacity', (t > 0.02 && t < 0.96 ? 0.9 : 0).toFixed(2));
    line.setAttribute('x1', scanX.toFixed(1)); line.setAttribute('x2', scanX.toFixed(1));
    line.setAttribute('opacity', (t > 0.02 && t < 0.96 ? 0.85 : 0).toFixed(2));
    for (let i = 0; i < barEls.length; i++) {
      const el = barEls[i], bx = +el.getAttribute('data-x'), bw = +el.getAttribute('data-w'), crit = el.getAttribute('data-crit') === '1';
      const passed = scanX >= bx;
      el.setAttribute('opacity', passed ? '0.95' : (clamp((t - 0.02) / 0.1) * 0.35).toFixed(2));
      el.setAttribute('width', (bw * (passed ? 1 : clamp(t / 0.15))).toFixed(1));
      el.setAttribute('fill', passed ? (crit ? '#2563eb' : '#9fb2d0') : '#c2ccdd');
    }
    const cpp = ease(clamp((t - 0.15) / 0.7));
    cp.setAttribute('opacity', clamp((t - 0.12) / 0.1).toFixed(2));
    cp.setAttribute('stroke-dasharray', '100 100'); cp.setAttribute('stroke-dashoffset', (100 - cpp * 100).toFixed(1));
    bf.style.width = (f.reveal ? 100 : f.display).toFixed(1) + '%';
    if (f.pct !== lastPct) { lastPct = f.pct; pct.textContent = f.pct + '%'; }
    if (f.label !== lastLabel) { lastLabel = f.label; st1.textContent = f.label; st2.textContent = f.label; }
  };
}

// Plays the presentation over the feature's panel, runs `work` (compute + render; may be
// async) UNDER it right after the overlay's first paint, and lifts the overlay in the frame
// the bar reaches 100% (results already painted). Resolves once the overlay starts lifting.
function runReveal(host, o) {
  const work = typeof o.work === 'function' ? o.work : null;
  const runWork = () => Promise.resolve().then(() => (work ? work() : undefined));
  if (!host || typeof document === 'undefined') {
    return runWork().catch(() => {});
  }
  injectCss();
  installRequestTap(window);
  const reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const model = createRevealModel({ reduce });

  const mount = mountFor(host);
  const prevPos = mount.style.position, prevMin = mount.style.minHeight;
  if (getComputedStyle(mount).position === 'static') mount.style.position = 'relative';
  if (mount.offsetHeight < MOUNT_MIN_H) mount.style.minHeight = MOUNT_MIN_H + 'px';

  const ov = buildOverlay(o.title || 'Analysis', o.iconPath || MARK);
  mount.appendChild(ov);
  const paint = makePainter(ov);
  REVEAL_WATCHERS.add(model);

  let raf = null, finished = false, started = false, settleTimer = null, capTimer = null, startTimer = null;
  let resolveDone;
  const done = new Promise(r => { resolveDone = r; });

  function finish() {
    if (finished) return; finished = true;
    REVEAL_WATCHERS.delete(model);
    if (raf) cancelAnimationFrame(raf);
    clearTimeout(settleTimer); clearTimeout(capTimer); clearTimeout(startTimer);
    ov.classList.add('out');                         // same frame as the 100% paint — no hold
    setTimeout(() => {
      if (ov.parentNode) ov.parentNode.removeChild(ov);
      mount.style.position = prevPos;
      mount.style.minHeight = prevMin;
    }, reduce ? 0 : 110);                           // just after the card's 0.1 s fade
    resolveDone();
  }

  function step(now) {
    raf = null;
    if (finished) return;
    if (!ov.isConnected) {                           // something cleared the mount — put the card back
      if (mount.isConnected) mount.appendChild(ov); else { finish(); return; }
    }
    const f = model.frame(now);
    paint(f);
    if (f.reveal) { finish(); return; }
    raf = requestAnimationFrame(step);
  }

  function start() {
    if (started || finished) return; started = true;
    clearTimeout(startTimer);
    model.workStarted(nowMs());
    const parts = [runWork()];
    if (o.gate) parts.push(Promise.resolve(o.gate));
    Promise.all(parts.map(p => p.catch(() => {}))).then(() => {
      model.settled(nowMs());
      // rAF is paused while the window is hidden/minimised: reveal anyway (results are in the DOM).
      settleTimer = setTimeout(() => {
        if (finished) return;
        paint({ stage: 'painted', display: 100, pct: 100, label: LABELS.painted, reveal: true });
        finish();
      }, SETTLE_FALLBACK_MS);
    });
  }

  raf = requestAnimationFrame(step);
  // Start the work once the overlay has been painted, so the results always build BEHIND it.
  requestAnimationFrame(() => setTimeout(start, 0));
  startTimer = setTimeout(start, 250);               // rAF paused (hidden window) → start anyway
  capTimer = setTimeout(finish, MAX_WAIT_MS);
  return done;
}

// Shared "run a feature" presentation — THE default for every feature's Run action.
// `work` computes + renders the results (sync or async). The bar reaches 100% only once
// `work` has settled and its results have been painted; the overlay then lifts at once.
// New features: call this with the element your results render into (any element inside
// the feature's .view-panel) — the overlay mounts on the panel itself.
export function revealAndRun(host, title, work, opts) {
  opts = opts || {};
  return runReveal(host, { title, iconPath: opts.iconPath, work });
}

// Compatibility wrapper: { onDone } is the work (run under the overlay); { gate } is an
// extra promise the reveal also waits for before reaching 100%.
export function playFeatureReveal(host, opts) {
  opts = opts || {};
  return runReveal(host, { title: opts.title, iconPath: opts.iconPath, work: opts.onDone, gate: opts.gate });
}

export default playFeatureReveal;
