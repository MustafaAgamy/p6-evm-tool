// Feature-open reveal — a short (~2.2s) branded "opening this feature" transition in
// the same motion family as the startup splash (boot.js), adapted to the light content
// area. Overlays `host`, plays, then fades out, removes itself, and calls opts.onDone so
// the real results render underneath. Self-contained (injects its own CSS once).
//
//   playFeatureReveal(hostEl, { title, iconPath?, durationMs?, onDone? })

let injected = false;
const MARK = 'M4 19V5M4 15l5-5 4 3 7-8';

function injectCss() {
  if (injected) return; injected = true;
  const css = `
  /* Opaque (mode-aware) so the results rendered UNDERNEATH at t>=0.62 stay fully
     hidden until the bar hits 100% — then the overlay lifts to reveal them. A
     translucent overlay used to let results show through before 100% (bug). */
  .fr-ov{position:absolute; inset:0; z-index:60; display:grid; place-items:center; opacity:0;
    background:var(--bg); transition:opacity .18s ease;
    font-family:"Segoe UI",system-ui,-apple-system,sans-serif;}
  .fr-ov.in{opacity:1;} .fr-ov.out{opacity:0;}
  .fr-card{width:min(400px,86%); background:#fff; border:1px solid #e2e8f0; border-radius:16px;
    box-shadow:0 24px 60px -24px rgba(15,23,42,.4); padding:20px 22px 18px;}
  .fr-hd{display:flex; align-items:center; gap:13px; margin-bottom:15px;}
  .fr-ic{width:44px; height:44px; flex:none; border-radius:12px; display:grid; place-items:center;
    background:linear-gradient(135deg,rgba(246,167,35,.18),rgba(37,99,235,.16)); }
  .fr-ic svg{width:24px; height:24px;}
  .fr-eb{font:700 9.5px/1 Archivo,system-ui,sans-serif; letter-spacing:.18em; text-transform:uppercase; color:#2563eb;}
  .fr-ti{font:800 17px/1.15 Archivo,system-ui,sans-serif; color:#1e293b; margin-top:3px;}
  .fr-st{font-size:12px; color:#64748b; margin-top:2px;}
  .fr-viz{width:100%; height:74px; display:block; margin:4px 0 13px;}
  .fr-tr{height:4px; border-radius:4px; background:#e8edf5; overflow:hidden;}
  .fr-bf{height:100%; width:0%; border-radius:4px; background:linear-gradient(90deg,#f6a723,#2563eb);}
  .fr-pc{display:flex; justify-content:space-between; margin-top:7px; font:600 10.5px/1 "Segoe UI",system-ui;
    letter-spacing:.06em; text-transform:uppercase; color:#94a3b8;}
  .fr-pc b{color:#1e293b; font-variant-numeric:tabular-nums; font-family:Archivo,system-ui,sans-serif;}
  @media (prefers-reduced-motion: reduce){ .fr-ov{transition:opacity .18s ease;} }`;
  const s = document.createElement('style'); s.id = 'fr-reveal-style'; s.textContent = css; document.head.appendChild(s);
}

const clamp = (x, a, b) => { a = a == null ? 0 : a; b = b == null ? 1 : b; return x < a ? a : x > b ? b : x; };
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3);
const STAGES = [[0, 'Reading schedule'], [0.28, 'Mapping logic'], [0.55, 'Analysing'], [0.80, 'Compiling results'], [0.95, 'Ready']];

export function playFeatureReveal(host, opts) {
  opts = opts || {};
  const onDone = typeof opts.onDone === 'function' ? opts.onDone : function () {};
  if (!host) { try { onDone(); } catch (e) {} return; }
  const DUR = opts.durationMs || 2200;
  const title = opts.title || 'Analysis';
  const iconPath = opts.iconPath || MARK;
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  injectCss();

  const prevPos = getComputedStyle(host).position;
  if (prevPos === 'static') host.style.position = 'relative';

  const ov = document.createElement('div');
  ov.className = 'fr-ov';
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
        <div><div class="fr-eb">Controlyx</div><div class="fr-ti">${title}</div><div class="fr-st"><span class="fr-stt">Reading schedule</span>…</div></div>
      </div>
      <svg class="fr-viz" viewBox="0 0 ${W} 74" preserveAspectRatio="none">
        <defs><linearGradient id="frscan" x1="0" x2="1"><stop offset="0" stop-color="#2563eb" stop-opacity="0"/><stop offset="1" stop-color="#2563eb" stop-opacity=".22"/></linearGradient></defs>
        <path class="frcp" d="M12 60 L120 50 L210 40 L300 22 L348 14" fill="none" stroke="#5b9bff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" pathLength="100" opacity="0"/>
        <g class="frbars">${bars}</g>
        <rect class="frscanband" x="0" y="0" width="46" height="74" fill="url(#frscan)" opacity="0"/>
        <line class="frscanline" x1="0" y1="0" x2="0" y2="74" stroke="#2563eb" stroke-width="2" opacity="0"/>
      </svg>
      <div class="fr-tr"><div class="fr-bf"></div></div>
      <div class="fr-pc"><span class="fr-stt2">Reading schedule</span><b class="fr-pct">0%</b></div>
    </div>`;
  host.appendChild(ov);
  requestAnimationFrame(() => ov.classList.add('in'));

  const barEls = [].slice.call(ov.querySelectorAll('.frb'));
  const cp = ov.querySelector('.frcp'), band = ov.querySelector('.frscanband'), line = ov.querySelector('.frscanline'),
        bf = ov.querySelector('.fr-bf'), pct = ov.querySelector('.fr-pct'), st1 = ov.querySelector('.fr-stt'), st2 = ov.querySelector('.fr-stt2');

  function render(t) {
    t = clamp(t, 0, 1);
    const scanX = t * W;
    band.setAttribute('x', (scanX - 46).toFixed(1)); band.setAttribute('opacity', (t > 0.02 && t < 0.96 ? 0.9 : 0).toFixed(2));
    line.setAttribute('x1', scanX.toFixed(1)); line.setAttribute('x2', scanX.toFixed(1));
    line.setAttribute('opacity', (t > 0.02 && t < 0.96 ? 0.85 : 0).toFixed(2));
    for (let i = 0; i < barEls.length; i++) {
      const el = barEls[i], bx = +el.getAttribute('data-x'), bw = +el.getAttribute('data-w'), crit = el.getAttribute('data-crit') === '1';
      const passed = scanX >= bx;
      el.setAttribute('opacity', passed ? '0.95' : (clamp((t - 0.02) / 0.1) * 0.35).toFixed(2));
      el.setAttribute('width', (bw * (passed ? 1 : clamp((t) / 0.15))).toFixed(1));
      el.setAttribute('fill', passed ? (crit ? '#2563eb' : '#9fb2d0') : '#c2ccdd');
    }
    const cpp = ease(clamp((t - 0.15) / 0.7));
    cp.setAttribute('opacity', clamp((t - 0.12) / 0.1).toFixed(2));
    cp.setAttribute('stroke-dasharray', '100 100'); cp.setAttribute('stroke-dashoffset', (100 - cpp * 100).toFixed(1));
    bf.style.width = (t * 100).toFixed(1) + '%'; pct.textContent = Math.round(t * 100) + '%';
    let s = STAGES[0][1]; for (let j = 0; j < STAGES.length; j++) if (t >= STAGES[j][0]) s = STAGES[j][1];
    if (st1.textContent !== s) { st1.textContent = s; st2.textContent = s; }
  }

  let raf = null, start = null, finished = false, onDoneFired = false;
  function fireOnce() { if (!onDoneFired) { onDoneFired = true; try { onDone(); } catch (e) {} } }
  function finish() {
    if (finished) return; finished = true;
    if (raf) cancelAnimationFrame(raf);
    fireOnce();                                   // ensure results are rendered by now
    ov.classList.remove('in'); ov.classList.add('out');
    setTimeout(() => {
      if (ov.parentNode) ov.parentNode.removeChild(ov);
      if (prevPos === 'static') host.style.position = '';
    }, 190);
  }

  if (reduce) { render(1); fireOnce(); setTimeout(finish, 120); return; }
  render(0);
  function step(ts) {
    if (finished) return;
    if (start == null) start = ts;
    const t = (ts - start) / DUR;
    render(t);
    // Render the results UNDER the overlay a touch before the bar completes, so the moment
    // it hits 100% the overlay lifts to reveal ready results — no wait after 100% (issue #05).
    if (t >= 0.62) fireOnce();
    if (t < 1) raf = requestAnimationFrame(step); else finish();
  }
  raf = requestAnimationFrame(step);
  setTimeout(() => { if (!finished) finish(); }, DUR + 900);   // safety cap (throttled rAF)
}

export default playFeatureReveal;
