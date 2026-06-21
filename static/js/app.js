import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initReaderHighlight, renderContent } from './reader-highlight.js';
import { initPlayer, stop, seekToSentence, updateMiniPlayer, prepareControls } from './player.js';
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
    if (state.playingItemId === itemId) {
      stop();
    }
    if (state.currentItemId === itemId) {
      state.currentItemId = null;
      state.currentItem = null;
      showView('empty');
    }
    updateMiniPlayer();
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
    if (data.item_id === state.playingItemId) {
      stop();
    }
    if (data.item_id === state.currentItemId) {
      state.currentItemId = null;
      state.currentItem = null;
      showView('empty');
    }
    updateMiniPlayer();
    loadView(state.currentView);
  },
});

miniPlayer.addEventListener('click', () => {
  if (state.playingItemId) {
    openItem(state.playingItemId);
  }
});

loadView('recent');
loadCollections();

// --- Core ---
async function openItem(itemId) {
  state.currentItemId = itemId;
  const version = ++openItemVersion;

  const data = await api(`/api/library/${itemId}`);
  if (data.error || version !== openItemVersion) return;

  state.currentItem = data.item;

  document.querySelectorAll('.item').forEach(el => el.classList.remove('is-active'));

  if (!data.item.audio_ready && data.item.interrupted) {
    showView('interrupted');
    updateMiniPlayer();
    return;
  }

  showView('player');
  renderContent(data.item);

  const isPlaying = itemId === state.playingItemId;

  if (isPlaying) {
    // Viewing the item whose audio is loaded — show full controls, sync timeline.
    state.timeline = data.item.timeline || [];
    state.totalDurationMs = data.item.total_duration_ms;
    controlsEl.classList.remove('is-hidden');
  } else if (data.item.audio_ready) {
    // Viewing a non-playing item that has audio — show controls without loading.
    controlsEl.classList.remove('is-hidden');
    prepareControls(data.item);
  } else {
    controlsEl.classList.add('is-hidden');
  }

  updateMiniPlayer();
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
