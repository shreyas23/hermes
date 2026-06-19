import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initReaderHighlight, renderContent } from './reader-highlight.js';
import { initPlayer, loadAudio, stop, saveProgress } from './player.js';
import { initModal } from './modal.js';

const emptyState = document.getElementById('empty-state');
const playerState = document.getElementById('player-state');
const miniPlayer = document.getElementById('mini-player');
const controlsEl = document.querySelector('.controls');

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

initReaderHighlight();
initPlayer();

initModal({
  onImport: (itemId, autoOpen = true) => {
    loadView(state.currentView);
    if (autoOpen) openItem(itemId);
  },
});

connectSSE({
  generation_progress: (data) => {
    const pct = Math.round((data.done / data.total) * 100);
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

  const data = await api(`/api/library/${itemId}`);
  if (data.error) return;

  state.currentItem = data.item;
  state.timeline = data.item.timeline || [];
  state.totalDurationMs = data.item.total_duration_ms;

  document.querySelectorAll('.item').forEach(el => el.classList.remove('is-active'));

  showView('player');
  renderContent(data.item);

  if (data.item.audio_ready) {
    controlsEl.classList.remove('is-hidden');
    loadAudio(data.item);
  } else {
    controlsEl.classList.add('is-hidden');
  }
}

function showView(view) {
  emptyState.classList.toggle('is-hidden', view !== 'empty');
  playerState.classList.toggle('is-visible', view === 'player');
}
