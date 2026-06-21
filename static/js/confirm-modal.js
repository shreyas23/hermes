// Promise-based confirmation modal — a styled replacement for window.confirm().
// Usage: if (await confirmAction({ title, message, confirmLabel })) { ... }

let resolver = null;

const backdrop = () => document.getElementById('confirm-modal');

export function initConfirm() {
  document.getElementById('confirm-backdrop').addEventListener('click', () => settle(false));
  document.getElementById('confirm-cancel').addEventListener('click', () => settle(false));
  document.getElementById('confirm-ok').addEventListener('click', () => settle(true));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && backdrop().classList.contains('is-visible')) settle(false);
  });
}

export function confirmAction({ title = 'Are you sure?', message = '', confirmLabel = 'Delete', destructive = true } = {}) {
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-message').textContent = message;
  const ok = document.getElementById('confirm-ok');
  ok.textContent = confirmLabel;
  ok.classList.toggle('modal__submit--destructive', destructive);
  backdrop().classList.add('is-visible');
  return new Promise(resolve => { resolver = resolve; });
}

function settle(result) {
  backdrop().classList.remove('is-visible');
  if (resolver) {
    resolver(result);
    resolver = null;
  }
}
