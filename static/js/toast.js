// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

const container = document.getElementById('toast-container');

export function toast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast${type !== 'info' ? ` toast--${type}` : ''}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

export function toastError(message) {
  toast(message, 'error');
}

export function toastSuccess(message) {
  toast(message, 'success');
}
