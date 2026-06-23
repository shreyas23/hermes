let resolver = null;
let isPromptMode = false;

const backdrop = () => document.getElementById('confirm-modal');
const inputEl = () => document.getElementById('confirm-input');

export function initConfirm() {
  document.getElementById('confirm-backdrop').addEventListener('click', () => settle(false));
  document.getElementById('confirm-cancel').addEventListener('click', () => settle(false));
  document.getElementById('confirm-ok').addEventListener('click', () => settle(true));
  inputEl().addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); settle(true); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && backdrop().classList.contains('is-visible')) settle(false);
  });
}

function setupOk({ confirmLabel, destructive }) {
  const ok = document.getElementById('confirm-ok');
  ok.textContent = confirmLabel;
  ok.classList.toggle('modal__submit--destructive', destructive);
}

export function confirmAction({ title = 'Are you sure?', message = '', confirmLabel = 'Delete', destructive = true } = {}) {
  isPromptMode = false;
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-message').textContent = message;
  inputEl().classList.add('is-hidden');
  setupOk({ confirmLabel, destructive });
  backdrop().classList.add('is-visible');
  return new Promise(resolve => { resolver = resolve; });
}

export function promptAction({ title = '', message = '', placeholder = '', confirmLabel = 'OK' } = {}) {
  isPromptMode = true;
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-message').textContent = message;
  const input = inputEl();
  input.classList.remove('is-hidden');
  input.value = '';
  input.placeholder = placeholder;
  setupOk({ confirmLabel, destructive: false });
  backdrop().classList.add('is-visible');
  setTimeout(() => input.focus(), 50);
  return new Promise(resolve => { resolver = resolve; });
}

function settle(accepted) {
  backdrop().classList.remove('is-visible');
  if (resolver) {
    if (isPromptMode) {
      resolver(accepted ? inputEl().value.trim() || null : null);
    } else {
      resolver(accepted);
    }
    resolver = null;
  }
}
