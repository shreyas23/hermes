const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2];

const state = {
  currentItemId: null,
  currentItem: null,
  playing: false,
  audio: new Audio(),
  timeline: [],
  totalDurationMs: 0,
  tickInterval: null,
  progressSaveInterval: null,
  eventSource: null,
  currentView: 'recent',
  speedIndex: 2,
  scrubbing: false,
};

// --- DOM refs ---
const itemList = document.getElementById('item-list');
const emptyState = document.getElementById('empty-state');
const generatingState = document.getElementById('generating-state');
const playerState = document.getElementById('player-state');
const sentencesContainer = document.getElementById('sentences-container');
const btnPlay = document.getElementById('btn-play');
const btnPause = document.getElementById('btn-pause');
const btnStop = document.getElementById('btn-stop');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnSpeed = document.getElementById('btn-speed');
const btnBack15 = document.getElementById('btn-back15');
const btnFwd15 = document.getElementById('btn-fwd15');
const scrubber = document.getElementById('scrubber');
const timeCurrent = document.getElementById('time-current');
const timeTotal = document.getElementById('time-total');
const statusText = document.getElementById('status-text');
const sentenceCounter = document.getElementById('sentence-counter');
const genTitle = document.getElementById('gen-title');
const genProgressFill = document.getElementById('gen-progress-fill');
const genStatus = document.getElementById('gen-status');
const importModal = document.getElementById('import-modal');
const collectionsList = document.getElementById('collections-list');
const miniPlayer = document.getElementById('mini-player');
const miniTitle = document.getElementById('mini-title');
const miniTime = document.getElementById('mini-time');
const miniPlay = document.getElementById('mini-play');
const miniPause = document.getElementById('mini-pause');
const miniProgressFill = document.getElementById('mini-progress-fill');

// --- API ---
async function api(path, opts = {}) {
  try {
    const res = await fetch(path, {
      method: opts.method || (opts.body ? 'POST' : 'GET'),
      headers: opts.body ? { 'Content-Type': 'application/json' } : {},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    return res.json();
  } catch (e) {
    console.error('API error:', e);
    return { error: e.message };
  }
}

// --- Init ---
connectSSE();
loadView('recent');
loadCollections();

// --- Navigation ---
document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.nav-item, .collection-item').forEach(e => e.classList.remove('active'));
    el.classList.add('active');
    state.currentView = el.dataset.view;
    loadView(el.dataset.view);
  });
});

async function loadView(view) {
  let params;
  switch (view) {
    case 'recent': params = '?view=recent'; break;
    case 'in_progress': params = '?view=in_progress'; break;
    case 'articles': params = '?source_type=article'; break;
    case 'documents': params = '?source_type=document'; break;
    case 'texts': params = '?source_type=text'; break;
    default: params = ''; break;
  }
  const data = await api(`/api/library${params}`);
  if (data.items) renderItemList(data.items);
}

async function loadCollection(id) {
  const data = await api(`/api/library?view=collection&collection_id=${id}`);
  if (data.items) renderItemList(data.items);
}

function renderItemList(items) {
  itemList.innerHTML = '';
  if (items.length === 0) {
    itemList.innerHTML = '<div style="padding:20px;color:#555;text-align:center;font-size:13px">No items yet</div>';
    return;
  }
  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'item-entry' + (item.id === state.currentItemId ? ' active' : '');
    const dur = item.audio_ready ? formatTime(item.total_duration_ms) : '';
    const badge = item.audio_ready
      ? ''
      : '<span class="item-badge badge-generating">generating</span>';

    let progress = '';
    if (item.progress && item.progress.current_time_ms > 0 && !item.progress.is_finished && item.total_duration_ms > 0) {
      const pct = Math.round((item.progress.current_time_ms / item.total_duration_ms) * 100);
      progress = `<div class="item-progress-bar"><div class="item-progress-fill" style="width:${pct}%"></div></div>`;
    }

    el.innerHTML = `
      <div class="item-title">${escHtml(item.title)}</div>
      <div class="item-meta">
        <span>${item.source_type}</span>
        ${dur ? `<span>${dur}</span>` : ''}
        ${badge}
      </div>
      ${progress}
    `;
    el.addEventListener('click', () => openItem(item.id));
    itemList.appendChild(el);
  });
}

// --- Open item ---
async function openItem(itemId) {
  saveProgress();
  stopPlayback();
  state.currentItemId = itemId;

  document.querySelectorAll('.item-entry').forEach(e => e.classList.remove('active'));

  const data = await api(`/api/library/${itemId}`);
  if (data.error) return;

  state.currentItem = data.item;
  state.timeline = data.item.timeline || [];
  state.totalDurationMs = data.item.total_duration_ms;

  if (!data.item.audio_ready) {
    showGenerating(data.item.title);
    return;
  }

  showPlayer(data.item);
}

function showGenerating(title) {
  emptyState.style.display = 'none';
  generatingState.style.display = '';
  playerState.style.display = 'none';
  genTitle.textContent = title;
  genStatus.textContent = 'Generating audio...';
  genProgressFill.style.width = '0%';
}

document.getElementById('gen-cancel').addEventListener('click', async () => {
  if (!state.currentItemId) return;
  await api(`/api/library/${state.currentItemId}/cancel`, { body: {} });
  state.currentItemId = null;
  state.currentItem = null;
  generatingState.style.display = 'none';
  emptyState.style.display = '';
  loadView(state.currentView);
});

function showPlayer(item) {
  emptyState.style.display = 'none';
  generatingState.style.display = 'none';
  playerState.style.display = '';

  renderSentences(item.sentences);
  timeTotal.textContent = formatTime(item.total_duration_ms);
  timeCurrent.textContent = '0:00';
  scrubber.value = 0;
  statusText.textContent = item.title;
  sentenceCounter.textContent = `${item.sentences.length} sentences`;

  state.audio.src = `/api/library/${item.id}/audio`;
  state.audio.playbackRate = SPEED_OPTIONS[state.speedIndex];
  state.audio.load();

  if (item.progress && item.progress.current_time_ms > 0 && !item.progress.is_finished) {
    const resumeMs = item.progress.current_time_ms;
    state.audio.addEventListener('canplay', function onCanPlay() {
      state.audio.currentTime = resumeMs / 1000;
      highlightCurrentSentence();
      state.audio.removeEventListener('canplay', onCanPlay);
    });
  }

  updateMiniPlayer();
}

// --- Sentences ---
function renderSentences(sentences) {
  sentencesContainer.innerHTML = '';
  sentences.forEach((text, i) => {
    const el = document.createElement('div');
    el.className = 'sentence';
    el.dataset.index = i;
    el.textContent = text;
    el.addEventListener('click', () => {
      if (state.timeline[i]) {
        state.audio.currentTime = state.timeline[i].start_ms / 1000;
        if (!state.playing) {
          state.audio.play();
          state.playing = true;
          syncPlayPauseButtons();
          startTick();
        }
        highlightCurrentSentence();
      }
    });
    sentencesContainer.appendChild(el);
  });
}

function getCurrentSentenceIndex() {
  if (!state.timeline.length) return -1;
  const currentMs = state.audio.currentTime * 1000;
  for (let i = state.timeline.length - 1; i >= 0; i--) {
    if (currentMs >= state.timeline[i].start_ms) return i;
  }
  return 0;
}

function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  const els = sentencesContainer.querySelectorAll('.sentence');
  els.forEach((el, i) => {
    el.classList.remove('active', 'near', 'played');
    if (i === index) el.classList.add('active');
    else if (Math.abs(i - index) <= 2) el.classList.add('near');
    else if (i < index) el.classList.add('played');
  });

  const activeEl = sentencesContainer.querySelector('.sentence.active');
  if (activeEl) {
    const container = sentencesContainer;
    const containerRect = container.getBoundingClientRect();
    const elRect = activeEl.getBoundingClientRect();
    const target = container.scrollTop + elRect.top - containerRect.top - containerRect.height / 2 + elRect.height / 2;
    container.scrollTo({ top: target, behavior: 'smooth' });
  }
}

// --- Playback ---
function play() {
  if (!state.currentItem || !state.currentItem.audio_ready) return;
  state.audio.play();
  state.playing = true;
  syncPlayPauseButtons();
  startTick();
  startProgressSave();
  updateMiniPlayer();
}

function pause() {
  state.audio.pause();
  state.playing = false;
  syncPlayPauseButtons();
  stopTick();
  stopProgressSave();
  saveProgress();
  updateMiniPlayer();
}

function syncPlayPauseButtons() {
  btnPlay.style.display = state.playing ? 'none' : '';
  btnPause.style.display = state.playing ? '' : 'none';
  miniPlay.style.display = state.playing ? 'none' : '';
  miniPause.style.display = state.playing ? '' : 'none';
}

btnPlay.addEventListener('click', play);
btnPause.addEventListener('click', pause);
btnStop.addEventListener('click', () => { saveProgress(); stopPlayback(); });

btnPrev.addEventListener('click', () => {
  const idx = getCurrentSentenceIndex();
  if (idx > 0 && state.timeline[idx - 1]) {
    state.audio.currentTime = state.timeline[idx - 1].start_ms / 1000;
    highlightCurrentSentence();
  }
});

btnNext.addEventListener('click', () => {
  const idx = getCurrentSentenceIndex();
  if (idx < state.timeline.length - 1 && state.timeline[idx + 1]) {
    state.audio.currentTime = state.timeline[idx + 1].start_ms / 1000;
    highlightCurrentSentence();
  }
});

btnBack15.addEventListener('click', () => {
  state.audio.currentTime = Math.max(0, state.audio.currentTime - 15);
  highlightCurrentSentence();
});

btnFwd15.addEventListener('click', () => {
  state.audio.currentTime = Math.min(state.audio.duration || 0, state.audio.currentTime + 15);
  highlightCurrentSentence();
});

// --- Speed control ---
btnSpeed.addEventListener('click', () => {
  state.speedIndex = (state.speedIndex + 1) % SPEED_OPTIONS.length;
  const speed = SPEED_OPTIONS[state.speedIndex];
  state.audio.playbackRate = speed;
  btnSpeed.textContent = speed === 1 ? '1x' : `${speed}x`;
});

// --- Audio ended ---
state.audio.addEventListener('ended', () => {
  state.playing = false;
  syncPlayPauseButtons();
  stopTick();
  stopProgressSave();
  if (state.currentItemId) {
    api(`/api/library/${state.currentItemId}/progress`, {
      body: { current_sentence: state.timeline.length, current_time_ms: 0, is_finished: true }
    });
  }
  updateMiniPlayer();
});

function stopPlayback() {
  state.audio.pause();
  state.audio.currentTime = 0;
  state.playing = false;
  syncPlayPauseButtons();
  stopTick();
  stopProgressSave();
  scrubber.value = 0;
  timeCurrent.textContent = '0:00';
  const els = sentencesContainer.querySelectorAll('.sentence');
  els.forEach(el => el.classList.remove('active', 'near', 'played'));
}

// --- Progress saving ---
function saveProgress() {
  if (!state.currentItemId || !state.audio.src) return;
  api(`/api/library/${state.currentItemId}/progress`, {
    body: {
      current_sentence: getCurrentSentenceIndex(),
      current_time_ms: state.audio.currentTime * 1000,
      is_finished: false,
    }
  });
}

function startProgressSave() {
  stopProgressSave();
  state.progressSaveInterval = setInterval(saveProgress, 30000);
}

function stopProgressSave() {
  if (state.progressSaveInterval) {
    clearInterval(state.progressSaveInterval);
    state.progressSaveInterval = null;
  }
}

// --- Scrubber (fixed: only seek on release, not during drag) ---
scrubber.addEventListener('mousedown', () => { state.scrubbing = true; });
scrubber.addEventListener('touchstart', () => { state.scrubbing = true; });

scrubber.addEventListener('input', () => {
  const pct = scrubber.value / 10000;
  const targetMs = pct * state.totalDurationMs;
  timeCurrent.textContent = formatTime(targetMs);
});

scrubber.addEventListener('mouseup', finishScrub);
scrubber.addEventListener('touchend', finishScrub);
scrubber.addEventListener('change', finishScrub);

function finishScrub() {
  if (!state.scrubbing) return;
  state.scrubbing = false;
  const pct = scrubber.value / 10000;
  const targetMs = pct * state.totalDurationMs;
  state.audio.currentTime = targetMs / 1000;
  highlightCurrentSentence();
}

// --- Tick ---
function startTick() {
  stopTick();
  state.tickInterval = setInterval(() => {
    if (state.playing && !state.audio.paused && !state.scrubbing) {
      const currentMs = state.audio.currentTime * 1000;
      const total = state.totalDurationMs || 1;
      scrubber.value = Math.round((currentMs / total) * 10000);
      timeCurrent.textContent = formatTime(currentMs);
      highlightCurrentSentence();
      updateMiniPlayer();
    }
  }, 100);
}

function stopTick() {
  if (state.tickInterval) {
    clearInterval(state.tickInterval);
    state.tickInterval = null;
  }
}

// --- Mini player ---
function updateMiniPlayer() {
  if (!state.currentItem) {
    miniPlayer.style.display = 'none';
    return;
  }
  miniPlayer.style.display = 'flex';
  miniTitle.textContent = state.currentItem.title;
  const currentMs = state.audio.currentTime * 1000;
  const total = state.totalDurationMs || 1;
  miniTime.textContent = `${formatTime(currentMs)} / ${formatTime(total)}`;
  miniProgressFill.style.width = `${(currentMs / total) * 100}%`;
}

miniPlay.addEventListener('click', (e) => { e.stopPropagation(); play(); });
miniPause.addEventListener('click', (e) => { e.stopPropagation(); pause(); });

miniPlayer.addEventListener('click', () => {
  if (state.currentItemId && playerState.style.display === 'none') {
    openItem(state.currentItemId);
  }
});

// --- SSE ---
function connectSSE() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = new EventSource('/api/events');

  state.eventSource.addEventListener('generation_progress', e => {
    const data = JSON.parse(e.data);
    if (data.item_id === state.currentItemId) {
      const pct = Math.round((data.done / data.total) * 100);
      genProgressFill.style.width = `${pct}%`;
      genStatus.textContent = `Generating audio... ${pct}%`;
    }
  });

  state.eventSource.addEventListener('generation_complete', e => {
    const data = JSON.parse(e.data);
    if (data.item_id === state.currentItemId) {
      openItem(state.currentItemId);
    }
    loadView(state.currentView);
  });

  state.eventSource.addEventListener('generation_cancelled', e => {
    const data = JSON.parse(e.data);
    if (data.item_id === state.currentItemId) {
      state.currentItemId = null;
      state.currentItem = null;
      generatingState.style.display = 'none';
      emptyState.style.display = '';
    }
    loadView(state.currentView);
  });
}

// --- Import modal ---
document.getElementById('btn-add').addEventListener('click', () => {
  importModal.style.display = '';
});

document.getElementById('import-backdrop').addEventListener('click', closeImport);
document.getElementById('import-close').addEventListener('click', closeImport);

function closeImport() {
  importModal.style.display = 'none';
}

document.querySelectorAll('.import-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.import-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.import-pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`pane-${tab.dataset.tab}`).classList.add('active');
  });
});

document.getElementById('import-url-btn').addEventListener('click', async () => {
  const url = document.getElementById('import-url').value.trim();
  if (!url) return;
  const btn = document.getElementById('import-url-btn');
  btn.textContent = 'Importing...';
  btn.disabled = true;
  const data = await api('/api/import/url', { body: { url } });
  btn.textContent = 'Import Article';
  btn.disabled = false;
  if (data.error) { alert(data.error); return; }
  closeImport();
  openItem(data.item_id);
  loadView(state.currentView);
});

document.getElementById('import-file-btn').addEventListener('click', async () => {
  const path = document.getElementById('import-file-path').value.trim();
  if (!path) return;
  const data = await api('/api/import/file', { body: { path } });
  if (data.error) { alert(data.error); return; }
  closeImport();
  openItem(data.item_id);
  loadView(state.currentView);
});

document.getElementById('import-folder-scan-btn').addEventListener('click', async () => {
  const folder = document.getElementById('import-folder-path').value.trim();
  if (!folder) return;
  const data = await api('/api/import/folder', { body: { folder } });
  if (data.error) { alert(data.error); return; }
  const results = document.getElementById('folder-scan-results');
  results.innerHTML = '';
  data.files.forEach(f => {
    const el = document.createElement('div');
    el.className = 'folder-file';
    el.innerHTML = `<span>${escHtml(f.name)}</span><button>Import</button>`;
    el.querySelector('button').addEventListener('click', async (e) => {
      const btn = e.target;
      btn.textContent = '...';
      const res = await api('/api/import/file', { body: { path: f.path } });
      if (res.error) { btn.textContent = 'Error'; return; }
      btn.textContent = 'Done';
      btn.classList.add('imported');
      loadView(state.currentView);
    });
    results.appendChild(el);
  });
});

document.getElementById('import-text-btn').addEventListener('click', async () => {
  const title = document.getElementById('import-text-title').value.trim() || 'Untitled';
  const text = document.getElementById('import-text-content').value.trim();
  if (!text) return;
  const data = await api('/api/import/text', { body: { title, text } });
  if (data.error) { alert(data.error); return; }
  closeImport();
  openItem(data.item_id);
  loadView(state.currentView);
});

// --- Collections ---
async function loadCollections() {
  const data = await api('/api/collections');
  if (!data.collections) return;
  collectionsList.innerHTML = '';
  data.collections.forEach(c => {
    const el = document.createElement('div');
    el.className = 'collection-item';
    el.textContent = `${c.name} (${c.count})`;
    el.addEventListener('click', () => {
      document.querySelectorAll('.nav-item, .collection-item').forEach(e => e.classList.remove('active'));
      el.classList.add('active');
      loadCollection(c.id);
    });
    collectionsList.appendChild(el);
  });
}

document.getElementById('btn-new-collection').addEventListener('click', async () => {
  const name = prompt('Collection name:');
  if (!name) return;
  await api('/api/collections', { body: { name } });
  loadCollections();
});

// --- Keyboard shortcuts ---
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch (e.code) {
    case 'Space':
      e.preventDefault();
      state.playing ? pause() : play();
      break;
    case 'ArrowLeft':
      e.preventDefault();
      btnPrev.click();
      break;
    case 'ArrowRight':
      e.preventDefault();
      btnNext.click();
      break;
    case 'Escape':
      if (importModal.style.display !== 'none') closeImport();
      else { saveProgress(); stopPlayback(); }
      break;
  }
});

// --- Save progress on window close ---
window.addEventListener('beforeunload', saveProgress);

// --- Helpers ---
function formatTime(ms) {
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec.toString().padStart(2, '0')}`;
}

function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
