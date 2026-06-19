import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initReaderHighlight, renderContent } from './reader-highlight.js';
import { initPlayer, loadAudio, stop, saveProgress, seekToSentence } from './player.js';
import { initModal } from './modal.js';
import { initSettings } from './settings.js';

const emptyState = document.getElementById('empty-state');
const playerState = document.getElementById('player-state');
const interruptedState = document.getElementById('interrupted-state');
const interruptedRetry = document.getElementById('interrupted-retry');
const miniPlayer = document.getElementById('mini-player');
const controlsEl = document.querySelector('.controls');

let openItemVersion = 0;

// --- Init ---
initSidebar({
  onOpen: openItem,
  onDelete: (itemId) => {
    if (state.currentItemId === itemId) {
      state.currentItemId = null;
      state.currentItem = null;
      stop();
      showView('empty');
      miniPlayer.classList.remove('is-visible');
      document.querySelector('.app').classList.remove('has-mini-player');
    }
  },
});

initReaderHighlight((si) => {
  if (state.currentItem?.audio_ready) seekToSentence(si);
});
initPlayer();
initSettings();

initModal({
  onImport: (itemId, autoOpen = true) => {
    loadView(state.currentView);
    if (autoOpen) openItem(itemId);
  },
});

connectSSE({
  generation_progress: (data) => {
    const total = data.total || 1;
    const pct = Math.round((data.done / total) * 100);
    updateGenerationProgress(data.item_id, pct);
  },
  generation_complete: (data) => {
    if (data.item_id === state.currentItemId) {
      openItem(state.currentItemId);
    }
    loadView(state.currentView);
  },
  generation_cancelled: (data) => {
    if (data.item_id === state.currentItemId) {
      state.currentItemId = null;
      state.currentItem = null;
      showView('empty');
    }
    loadView(state.currentView);
  },
});

miniPlayer.addEventListener('click', () => {
  if (state.currentItemId && !playerState.classList.contains('is-visible')) {
    openItem(state.currentItemId);
  }
});

loadView('recent');
loadCollections();

// --- Core ---
async function openItem(itemId) {
  saveProgress();
  stop();
  state.currentItemId = itemId;
  const version = ++openItemVersion;

  const data = await api(`/api/library/${itemId}`);
  if (data.error || version !== openItemVersion) return;

  state.currentItem = data.item;
  state.timeline = data.item.timeline || [];
  state.totalDurationMs = data.item.total_duration_ms;

  document.querySelectorAll('.item').forEach(el => el.classList.remove('is-active'));

  if (!data.item.audio_ready && data.item.interrupted) {
    showView('interrupted');
    return;
  }

  showView('player');
  renderContent(data.item);

  if (data.item.audio_ready) {
    controlsEl.classList.remove('is-hidden');
    loadAudio(data.item);
  } else {
    controlsEl.classList.add('is-hidden');
  }
}

interruptedRetry.addEventListener('click', async () => {
  const itemId = state.currentItemId;
  if (!itemId) return;
  const data = await api(`/api/library/${itemId}/retry`, { method: 'POST' });
  if (data.error) return;
  showView('empty');
  loadView(state.currentView);
});

function showView(view) {
  emptyState.classList.toggle('is-hidden', view !== 'empty');
  playerState.classList.toggle('is-visible', view === 'player');
  interruptedState.classList.toggle('is-visible', view === 'interrupted');
}
