import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initReaderHighlight, renderContent } from './reader-highlight.js';
import { initPlayer, play, pause, stop, seekToSentence, prepareControls } from './player.js';
import { initModal } from './modal.js';
import { initDiscover } from './discover.js';
import { initSettings } from './settings.js';
import { initConfirm } from './confirm-modal.js';
import { initSearch, resetSearch } from './search.js';
import { initBookmarks, loadBookmarks, resetBookmarks } from './bookmarks.js';
import { initQueue, removeItemById } from './queue.js';
import { initSleepTimer } from './sleep-timer.js';

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

// Generic close affordance: any modal X button closes its backdrop.
document.querySelectorAll('.modal__close').forEach(btn => {
  btn.addEventListener('click', () => btn.closest('.modal-backdrop')?.classList.remove('is-visible'));
});

// Opt-in audio generation controls.
document.getElementById('audio-gen-action').addEventListener('click', async () => {
  const id = state.currentItemId;
  if (!id) return;
  const data = await api(`/api/library/${id}/generate`, { method: 'POST' });
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
  },
  generation_cancelled: (data) => {
    // Cancelling generation returns the item to a pending state; it is not deleted.
    if (data.item_id === state.currentItemId) {
      openItem(state.currentItemId);
    }
    loadView(state.currentView);
  },
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
  const action = document.getElementById('audio-gen-action');
  const progress = document.getElementById('audio-gen-progress');
  const note = document.getElementById('audio-gen-note');
  if (item.generating) {
    action.classList.add('is-hidden');
    progress.classList.remove('is-hidden');
    note.textContent = '';
  } else {
    action.classList.remove('is-hidden');
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
