const MARGIN = 8;   // min gap between tooltip and viewport edge
const OFFSET = 8;   // gap between tooltip and the anchor element

export function initTooltips() {
  const tip = document.getElementById('g-tooltip');

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('[data-tooltip]');
    if (!el?.dataset.tooltip) {
      tip.classList.remove('visible');
      return;
    }

    tip.textContent = el.dataset.tooltip;
    // Hide while repositioning so it doesn't flash at the wrong spot
    tip.style.opacity = '0';
    tip.classList.add('visible');

    requestAnimationFrame(() => {
      const rect = el.getBoundingClientRect();
      const tw   = tip.offsetWidth;
      const th   = tip.offsetHeight;
      const vw   = window.innerWidth;
      const vh   = window.innerHeight;

      // Default: centred above the element
      let left = rect.left + rect.width  / 2 - tw / 2;
      let top  = rect.top  - th - OFFSET;

      // Clamp horizontally
      left = Math.max(MARGIN, Math.min(left, vw - tw - MARGIN));

      // Flip below if not enough room above
      if (top < MARGIN) top = rect.bottom + OFFSET;
      // If also no room below, just clamp to MARGIN from top
      if (top + th > vh - MARGIN) top = Math.max(MARGIN, vh - th - MARGIN);

      tip.style.left    = `${left}px`;
      tip.style.top     = `${top}px`;
      tip.style.opacity = '';   // let CSS transition take over
    });
  });

  document.addEventListener('mouseout', e => {
    const leaving  = e.target.closest('[data-tooltip]');
    if (!leaving) return;
    const entering = e.relatedTarget?.closest('[data-tooltip]');
    if (!entering) tip.classList.remove('visible');
  });
}
