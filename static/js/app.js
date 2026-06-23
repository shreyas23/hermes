import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initReaderHighlight, renderContent, toggleTeleprompter } from './reader-highlight.js';
import { initPlayer, play, pause, stop, seekToSentence, prepareControls } from './player.js';
import { initModal } from './modal.js';
import { initDiscover } from './discover.js';
import { initSettings } from './settings.js';
import { initConfirm } from './confirm-modal.js';
import { initSearch, resetSearch } from './search.js';
import { initBookmarks, loadBookmarks, resetBookmarks, addCurrent as addBookmark } from './bookmarks.js';
import { initQueue, removeItemById, advanceQueue } from './queue.js';
import { initSleepTimer } from './sleep-timer.js';
import { initDragDrop } from './drag-drop.js';
import { initDashboard, loadDashboard as _loadDashboard } from './dashboard.js';
const DASHBOARD_ENABLED = false;
const loadDashboard = DASHBOARD_ENABLED ? _loadDashboard : () => {};
import { toastSuccess, toastError } from './toast.js';

const emptyState = document.getElementById('empty-state');
const playerState = document.getElementById('player-state');
const controlsEl = document.querySelector('.controls');
const audioGen = document.getElementById('audio-gen');

let openItemVersion = 0;

// --- Init ---
initSidebar({
  onOpen: openItem,
  onDelete: (itemId) => {
    if (state.playingItemId === itemId) {
      stop();
    }
    removeItemById(itemId);
    if (state.currentItemId === itemId) {
      state.currentItemId = null;
      state.currentItem = null;
      showView('empty');
      loadDashboard();
    }
  },
});

initReaderHighlight((si) => {
  if (state.currentItem?.audio_ready) seekToSentence(si);
});
initPlayer();
initQueue({
  onPlay: async (itemId) => {
    await openItem(itemId);
    if (state.currentItemId === itemId && state.currentItem?.audio_ready) {
      play();
    }
  },
});
initSleepTimer({ onExpire: pause });
initSettings();
initConfirm();
initSearch();
initBookmarks({ onJump: seekToSentence });

const onImport = (itemId, autoOpen = true) => {
  loadView(state.currentView);
  if (autoOpen) openItem(itemId);
};
initModal({ onImport });
initDiscover({ onImport });
initDragDrop({ onImport });
if (DASHBOARD_ENABLED) initDashboard({ onOpen: openItem });

// Generic close affordance: any modal X button closes its backdrop.
document.querySelectorAll('.modal__close').forEach(btn => {
  btn.addEventListener('click', () => btn.closest('.modal-backdrop')?.classList.remove('is-visible'));
});

// Opt-in audio generation controls — split button with engine picker.
let selectedEngine = 'edge';
const genMenu = document.getElementById('audio-gen-menu');
api('/api/settings').then(s => {
  selectedEngine = s.tts_engine || 'edge';
  updateActiveEngine();
});

function updateActiveEngine() {
  genMenu.querySelectorAll('.audio-gen__menu-item').forEach(el => {
    el.classList.toggle('is-active', el.dataset.engine === selectedEngine);
  });
}

document.getElementById('audio-gen-caret').addEventListener('click', (e) => {
  e.stopPropagation();
  if (genMenu.classList.contains('is-visible')) {
    genMenu.classList.remove('is-visible');
    return;
  }
  const rect = e.currentTarget.getBoundingClientRect();
  genMenu.classList.add('is-visible');
  const menuH = genMenu.offsetHeight;
  const above = rect.top - menuH - 4;
  genMenu.style.left = `${rect.left + rect.width / 2 - 90}px`;
  genMenu.style.top = above >= 0 ? `${above}px` : `${rect.bottom + 4}px`;
});

genMenu.addEventListener('click', async (e) => {
  const item = e.target.closest('.audio-gen__menu-item');
  if (!item) return;
  selectedEngine = item.dataset.engine;
  updateActiveEngine();
  genMenu.classList.remove('is-visible');
  const id = state.currentItemId;
  if (!id) return;
  const data = await api(`/api/library/${id}/generate`, { method: 'POST', body: { engine: selectedEngine } });
  if (data.error) return;
  if (state.currentItem) state.currentItem.generating = true;
  renderAudioGen({ generating: true });
  loadView(state.currentView);
});

document.addEventListener('click', () => genMenu.classList.remove('is-visible'));

document.getElementById('audio-gen-action').addEventListener('click', async () => {
  const id = state.currentItemId;
  if (!id) return;
  const data = await api(`/api/library/${id}/generate`, { method: 'POST', body: { engine: selectedEngine } });
  if (data.error) return;
  if (state.currentItem) state.currentItem.generating = true;
  renderAudioGen({ generating: true });
  loadView(state.currentView);
});

document.getElementById('audio-gen-cancel').addEventListener('click', async () => {
  const id = state.currentItemId;
  if (!id) return;
  await api(`/api/library/${id}/cancel`, { method: 'POST' });
});

// --- App-level keyboard shortcuts ---
async function importFromClipboard(forceText = false) {
  try {
    const text = await navigator.clipboard.readText();
    if (!text?.trim()) { toastError('Clipboard is empty'); return; }
    const trimmed = text.trim();
    if (!forceText && /^https?:\/\//i.test(trimmed)) {
      toastSuccess('Importing URL...');
      const data = await api('/api/import/url', { body: { url: trimmed } });
      if (data.error) return;
      onImport(data.item_id);
    } else {
      toastSuccess('Importing text...');
      const title = trimmed.split('\n')[0].slice(0, 80) || 'Clipboard';
      const data = await api('/api/import/text', { body: { title, text: trimmed } });
      if (data.error) return;
      onImport(data.item_id);
    }
  } catch {
    toastError('Cannot read clipboard');
  }
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  const meta = e.metaKey || e.ctrlKey;

  if (meta && e.key === 'v') {
    e.preventDefault();
    importFromClipboard(e.shiftKey);
    return;
  }

  if (meta || e.altKey) return;

  switch (e.code) {
    case 'KeyB':
      e.preventDefault();
      addBookmark();
      break;
    case 'KeyN':
      e.preventDefault();
      advanceQueue();
      break;
    case 'KeyT':
      if (playerState.classList.contains('is-visible')) {
        e.preventDefault();
        toggleTeleprompter();
      }
      break;
    case 'Escape':
      if (playerState.classList.contains('is-visible') && !document.querySelector('.modal-backdrop.is-visible')) {
        showView('empty');
        loadDashboard();
      }
      break;
  }
});

connectSSE({
  generation_progress: (data) => {
    const total = data.total || 1;
    const pct = Math.round((data.done / total) * 100);
    updateGenerationProgress(data.item_id, pct);
    if (data.item_id === state.currentItemId && !state.currentItem?.audio_ready) {
      setGenProgress(pct);
    }
  },
  generation_complete: (data) => {
    if (data.item_id === state.currentItemId) {
      openItem(state.currentItemId);
    }
    loadView(state.currentView);
    loadDashboard();
  },
  generation_cancelled: (data) => {
    if (data.item_id === state.currentItemId) {
      openItem(state.currentItemId);
    }
    loadView(state.currentView);
  },
  watch_folder_import: () => {
    loadView(state.currentView);
    loadDashboard();
  },
});

loadView('recent');
loadCollections();
loadDashboard();

// --- Core ---
async function openItem(itemId) {
  state.currentItemId = itemId;
  const version = ++openItemVersion;

  const data = await api(`/api/library/${itemId}`);
  if (data.error || version !== openItemVersion) return;

  state.currentItem = data.item;
  const item = data.item;

  document.querySelectorAll('.item').forEach(el => el.classList.remove('is-active'));

  // The reader is always shown so text is readable before (or without) audio.
  showView('player');
  renderContent(item);
  resetSearch();
  resetBookmarks();
  loadBookmarks(item.id);

  const isPlaying = itemId === state.playingItemId;

  if (item.audio_ready) {
    hideAudioGen();
    controlsEl.classList.remove('is-hidden');
    if (isPlaying) {
      // Viewing the item whose audio is loaded — sync timeline.
      state.timeline = item.timeline || [];
      state.totalDurationMs = item.total_duration_ms;
    } else {
      prepareControls(item);
    }
  } else {
    // Pending / generating / interrupted — hide transport, show the audio-gen bar.
    controlsEl.classList.add('is-hidden');
    renderAudioGen(item);
  }
}

function renderAudioGen(item) {
  audioGen.classList.remove('is-hidden');
  const split = document.getElementById('audio-gen-split');
  const progress = document.getElementById('audio-gen-progress');
  const note = document.getElementById('audio-gen-note');
  genMenu.classList.remove('is-visible');
  if (item.generating) {
    split.classList.add('is-hidden');
    progress.classList.remove('is-hidden');
    note.textContent = '';
  } else {
    split.classList.remove('is-hidden');
    progress.classList.add('is-hidden');
    note.textContent = item.interrupted ? 'Audio generation was interrupted.' : '';
    setGenProgress(0);
  }
}

function hideAudioGen() {
  audioGen.classList.add('is-hidden');
}

function setGenProgress(pct) {
  document.getElementById('audio-gen-fill').style.width = `${pct}%`;
  document.getElementById('audio-gen-pct').textContent = `${pct}%`;
}

function showView(view) {
  emptyState.classList.toggle('is-hidden', view !== 'empty');
  playerState.classList.toggle('is-visible', view === 'player');
}
