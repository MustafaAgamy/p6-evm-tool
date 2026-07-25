export function initTheme() {
  const saved = localStorage.getItem('p6_evm_theme') || 'light';
  if (saved === 'light') document.documentElement.classList.add('light');
}

export function toggleTheme() {
  const isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('p6_evm_theme', isLight ? 'light' : 'dark');
}
