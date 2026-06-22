import { state } from './state.js';
import { formatTime, escHtml } from './utils.js';
import { toastSuccess } from './toast.js';

let onPlayQueueItem = null;

const panel = document.getElementById('queue-panel');
const listEl = document.getElementById('queue-list');
const btnQueue = document.getElementById('btn-queue');
const btnClear = document.getElementById('queue-clear');

export function initQueue({ onPlay }) {
  onPlayQueueItem = onPlay;
  btnQueue.addEventListener('click', togglePanel);
  btnClear.addEventListener('click', () => {
    state.queue = [];
    sync();
  });
}

export function addToQueue(item) {
  if (state.queue.some(q => q.id === item.id)) return;
  state.queue.push(pick(item));
  sync();
  toastSuccess('Added to queue');
}

export function playNext(item) {
  const existing = state.queue.findIndex(q => q.id === item.id);
  if (existing !== -1) state.queue.splice(existing, 1);
  state.queue.unshift(pick(item));
  sync();
  toastSuccess('Playing next');
}

function removeFromQueue(index) {
  state.queue.splice(index, 1);
  sync();
}

export function removeItemById(itemId) {
  const idx = state.queue.findIndex(q => q.id === itemId);
  if (idx !== -1) {
    state.queue.splice(idx, 1);
    sync();
  }
}

export async function advanceQueue() {
  if (state.queue.length === 0) return false;
  const next = state.queue.shift();
  sync();
  if (onPlayQueueItem) await onPlayQueueItem(next.id);
  return true;
}

function sync() {
  render();
  updateBadge();
}

function togglePanel() {
  panel.classList.toggle('is-hidden');
  btnQueue.classList.toggle('is-active', !panel.classList.contains('is-hidden'));
}

function pick(item) {
  return { id: item.id, title: item.title, source_type: item.source_type, total_duration_ms: item.total_duration_ms };
}

function render() {
  if (state.queue.length === 0) {
    listEl.innerHTML = '<div class="queue-panel__empty">Queue is empty</div>';
    btnClear.classList.add('is-hidden');
    return;
  }
  btnClear.classList.remove('is-hidden');
  listEl.innerHTML = '';
  state.queue.forEach((item, i) => {
    const el = document.createElement('div');
    el.className = 'queue-item';
    const dur = item.total_duration_ms ? formatTime(item.total_duration_ms) : '';
    el.innerHTML = `
      <span class="queue-item__index">${i + 1}</span>
      <div class="queue-item__info">
        <div class="queue-item__title">${escHtml(item.title)}</div>
        <div class="queue-item__meta">${item.source_type}${dur ? ' · ' + dur : ''}</div>
      </div>
      <button class="queue-item__remove" title="Remove">&times;</button>
    `;
    el.querySelector('.queue-item__remove').addEventListener('click', e => {
      e.stopPropagation();
      removeFromQueue(i);
    });
    listEl.appendChild(el);
  });
}

function updateBadge() {
  const n = state.queue.length;
  btnQueue.dataset.count = n || '';
}
