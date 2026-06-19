import { api, connectSSE } from './api.js';
import { state } from './state.js';
import { initSidebar, loadView, loadCollections, updateGenerationProgress } from './sidebar.js';
import { initTeleprompter, renderSentences, highlightCurrentSentence } from './teleprompter.js';
import { initPlayer, loadAudio, stop, saveProgress, seekToSentence } from './player.js';
import { initModal } from './modal.js';
import { escHtml } from './utils.js';

const emptyState = document.getElementById('empty-state');
const generatingState = document.getElementById('generating-state');
const playerState = document.getElementById('player-state');
const genTitle = document.getElementById('gen-title');
const genProgressFill = document.getElementById('gen-progress-fill');
const genStatus = document.getElementById('gen-status');
const miniPlayer = document.getElementById('mini-player');
const genCancel = document.getElementById('gen-cancel');
const genRetry = document.getElementById('gen-retry');
const teleprompterView = document.getElementById('teleprompter-view');
const readerView = document.getElementById('reader-view');
const readerContent = document.getElementById('reader-content');
const tabListen = document.getElementById('tab-listen');
const tabRead = document.getElementById('tab-read');
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

initTeleprompter({
  onClick: seekToSentence,
});

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

genCancel.addEventListener('click', async () => {
  if (!state.currentItemId) return;
  await api(`/api/library/${state.currentItemId}/cancel`, { body: {} });
  state.currentItemId = null;
  state.currentItem = null;
  showView('empty');
  miniPlayer.classList.remove('is-visible');
  loadView(state.currentView);
  loadCollections();
});

genRetry.addEventListener('click', async () => {
  if (!state.currentItemId) return;
  genRetry.classList.add('is-hidden');
  genCancel.classList.remove('is-hidden');
  genStatus.textContent = 'Generating audio...';
  genProgressFill.style.width = '0%';
  await api(`/api/library/${state.currentItemId}/retry`, { body: {} });
});

miniPlayer.addEventListener('click', () => {
  if (state.currentItemId && !playerState.classList.contains('is-visible')) {
    openItem(state.currentItemId);
  }
});

// --- Listen / Read tabs ---
tabListen.addEventListener('click', () => setMode('listen'));
tabRead.addEventListener('click', () => setMode('read'));

function setMode(mode) {
  tabListen.classList.toggle('is-active', mode === 'listen');
  tabRead.classList.toggle('is-active', mode === 'read');
  teleprompterView.classList.toggle('is-hidden', mode !== 'listen');
  readerView.classList.toggle('is-hidden', mode !== 'read');
}

function renderReader(item) {
  readerContent.innerHTML = '';
  const images = item.images || [];
  const imagesByPosition = {};
  images.forEach(img => {
    const pos = img.after_sentence;
    if (!imagesByPosition[pos]) imagesByPosition[pos] = [];
    imagesByPosition[pos].push(img);
  });

  item.sentences.forEach((text, i) => {
    const p = document.createElement('p');
    p.className = 'reader__paragraph';
    p.textContent = text;
    readerContent.appendChild(p);

    if (imagesByPosition[i]) {
      imagesByPosition[i].forEach(img => {
        const wrapper = document.createElement('div');
        wrapper.className = 'reader__image';
        const imgEl = document.createElement('img');
        imgEl.src = `/api/library/${item.id}/images/${img.filename}`;
        imgEl.alt = img.alt || '';
        imgEl.loading = 'lazy';
        wrapper.appendChild(imgEl);
        if (img.alt) {
          const caption = document.createElement('div');
          caption.className = 'reader__image-caption';
          caption.textContent = img.alt;
          wrapper.appendChild(caption);
        }
        readerContent.appendChild(wrapper);
      });
    }
  });
}

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

  // Re-highlight active item in sidebar
  document.querySelectorAll('.item').forEach(el => el.classList.remove('is-active'));

  renderReader(data.item);
  renderSentences(data.item.sentences, data.item.images || [], data.item.id);

  if (!data.item.audio_ready) {
    showView('player');
    setMode('read');
    tabListen.classList.add('is-hidden');
    controlsEl.classList.add('is-hidden');
    return;
  }

  tabListen.classList.remove('is-hidden');
  controlsEl.classList.remove('is-hidden');
  showView('player');
  setMode('listen');
  loadAudio(data.item);
}

function showView(view) {
  emptyState.classList.toggle('is-hidden', view !== 'empty');
  generatingState.classList.toggle('is-visible', view === 'generating');
  playerState.classList.toggle('is-visible', view === 'player');
}
