import { api } from './api.js';
import { state, SPEED_OPTIONS } from './state.js';
import { highlightCurrentSentence, getCurrentSentenceIndex, clearHighlights } from './reader-highlight.js';
import { formatTime } from './utils.js';
import { advanceQueue } from './queue.js';
import { checkEndOfItem } from './sleep-timer.js';

const btnPlay = document.getElementById('btn-play');
const btnPause = document.getElementById('btn-pause');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnSpeed = document.getElementById('btn-speed');
const btnBack15 = document.getElementById('btn-back15');
const btnFwd15 = document.getElementById('btn-fwd15');
const scrubber = document.getElementById('scrubber');
const timeCurrent = document.getElementById('time-current');
const timeTotal = document.getElementById('time-total');
const statusText = document.getElementById('status-text');
let canplayAbort = null;

// --- Global media keys (macOS routes them here via the Media Session API
// while audio is playing, even when Hermes isn't focused) ---
function setupMediaSession() {
  if (!('mediaSession' in navigator)) return;
  const ms = navigator.mediaSession;
  const handlers = {
    play,
    pause,
    previoustrack: () => btnPrev.click(),
    nexttrack: () => btnNext.click(),
    seekbackward: () => btnBack15.click(),
    seekforward: () => btnFwd15.click(),
  };
  const registered = [];
  for (const [action, fn] of Object.entries(handlers)) {
    try { ms.setActionHandler(action, fn); registered.push(action); } catch { /* unsupported action */ }
  }
  window.__mediaSessionActions = registered; // test seam
}

function updateMediaMetadata(item) {
  if (!('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return;
  navigator.mediaSession.metadata = new MediaMetadata({ title: item.title, artist: 'Hermes' });
}

function setPlaybackState(playbackState) {
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = playbackState;
}

function cycleSpeed(dir) {
  state.speedIndex = (state.speedIndex + dir + SPEED_OPTIONS.length) % SPEED_OPTIONS.length;
  const speed = SPEED_OPTIONS[state.speedIndex];
  state.audio.playbackRate = speed;
  btnSpeed.textContent = speed === 1 ? '1x' : `${speed}x`;
}

export function initPlayer() {
  btnPlay.addEventListener('click', play);
  btnPause.addEventListener('click', pause);
  setupMediaSession();

  btnPrev.addEventListener('click', () => {
    const idx = getCurrentSentenceIndex();
    if (idx > 0 && state.timeline[idx - 1]) {
      state.audio.currentTime = state.timeline[idx - 1].start_ms / 1000;
      highlightCurrentSentence();
    }
  });

  btnNext.addEventListener('click', () => {
    const idx = getCurrentSentenceIndex();
    if (idx < state.timeline.length - 1) {
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

  btnSpeed.addEventListener('click', () => cycleSpeed(1));
  btnSpeed.addEventListener('contextmenu', (e) => { e.preventDefault(); cycleSpeed(-1); });

  state.audio.addEventListener('ended', async () => {
    state.playing = false;
    syncButtons();
    setPlaybackState('none');
    stopTick();
    stopProgressSave();
    if (state.playingItemId) {
      api(`/api/library/${state.playingItemId}/progress`, {
        body: { current_sentence: state.timeline.length, current_time_ms: 0, is_finished: true }
      });
    }
    state.playingItemId = null;
    state.playingItem = null;
    if (checkEndOfItem()) return;
    await advanceQueue();
  });

  state.audio.addEventListener('play', () => {
    state.playing = true;
    syncButtons();
  });

  state.audio.addEventListener('pause', () => {
    if (!state.audio.ended) {
      state.playing = false;
      syncButtons();
    }
  });

  // Scrubber
  scrubber.addEventListener('mousedown', () => { state.scrubbing = true; });
  scrubber.addEventListener('touchstart', () => { state.scrubbing = true; }, { passive: true });

  scrubber.addEventListener('input', () => {
    const pct = scrubber.value / 10000;
    timeCurrent.textContent = formatTime(pct * state.totalDurationMs);
  });

  const finishScrub = () => {
    if (!state.scrubbing) return;
    state.scrubbing = false;
    state.audio.currentTime = (scrubber.value / 10000) * state.totalDurationMs / 1000;
    highlightCurrentSentence();
  };

  scrubber.addEventListener('mouseup', finishScrub);
  scrubber.addEventListener('touchend', finishScrub);
  scrubber.addEventListener('change', finishScrub);

  // Keyboard
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    switch (e.code) {
      case 'Space':
        if (!state.currentItem?.audio_ready) return;
        e.preventDefault();
        state.playing ? pause() : play();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        if (e.shiftKey) { btnBack15.click(); }
        else { btnPrev.click(); }
        break;
      case 'ArrowRight':
        e.preventDefault();
        if (e.shiftKey) { btnFwd15.click(); }
        else { btnNext.click(); }
        break;
      case 'BracketLeft':
        e.preventDefault();
        cycleSpeed(-1);
        break;
      case 'BracketRight':
        e.preventDefault();
        cycleSpeed(1);
        break;
    }
  });

  window.addEventListener('beforeunload', () => {
    const itemId = state.playingItemId;
    const src = state.audio.src;
    if (!itemId || !src) return;
    const currentSentence = getCurrentSentenceIndex();
    const currentTimeMs = state.audio.currentTime * 1000;
    const body = JSON.stringify({
      current_sentence: currentSentence,
      current_time_ms: currentTimeMs,
      is_finished: false,
    });
    navigator.sendBeacon(`/api/library/${itemId}/progress`, new Blob([body], { type: 'application/json' }));
  });
}

export function loadAudio(item) {
  if (canplayAbort) canplayAbort.abort();

  timeTotal.textContent = formatTime(item.total_duration_ms);
  timeCurrent.textContent = '0:00';
  scrubber.value = 0;
  statusText.textContent = item.title;
  state.playingItemId = item.id;
  state.playingItem = item;
  state.audio.src = `/api/library/${item.id}/audio`;
  state.audio.playbackRate = SPEED_OPTIONS[state.speedIndex];
  state.audio.load();
  updateMediaMetadata(item);

  if (item.progress && item.progress.current_time_ms > 0 && !item.progress.is_finished) {
    const resumeMs = item.progress.current_time_ms;
    canplayAbort = new AbortController();
    state.audio.addEventListener('canplay', () => {
      state.audio.currentTime = resumeMs / 1000;
      highlightCurrentSentence();
    }, { once: true, signal: canplayAbort.signal });
  }

}

export function play() {
  if (!state.currentItem || !state.currentItem.audio_ready) return;

  if (state.currentItemId !== state.playingItemId) {
    if (state.playingItemId) saveProgress();
    state.timeline = state.currentItem.timeline || [];
    state.totalDurationMs = state.currentItem.total_duration_ms;
    loadAudio(state.currentItem);
  }

  state.audio.play();
  state.playing = true;
  syncButtons();
  setPlaybackState('playing');
  startTick();
  startProgressSave();
}

export function pause() {
  state.audio.pause();
  state.playing = false;
  syncButtons();
  setPlaybackState('paused');
  stopTick();
  stopProgressSave();
  saveProgress();
}

export function stop() {
  state.audio.pause();
  state.audio.currentTime = 0;
  state.playing = false;
  syncButtons();
  setPlaybackState('none');
  stopTick();
  stopProgressSave();
  scrubber.value = 0;
  timeCurrent.textContent = '0:00';
  state.playingItemId = null;
  state.playingItem = null;
  clearHighlights();
}

export function seekToSentence(index) {
  const switching = state.currentItemId !== state.playingItemId;
  if (switching) {
    if (state.playingItemId) saveProgress();
    state.timeline = state.currentItem.timeline || [];
    state.totalDurationMs = state.currentItem.total_duration_ms;
    loadAudio(state.currentItem);
  }
  if (!state.timeline[index]) return;

  const seekSec = state.timeline[index].start_ms / 1000;
  const startPlay = () => {
    state.audio.currentTime = seekSec;
    if (!state.playing) {
      state.audio.play();
      state.playing = true;
      syncButtons();
      setPlaybackState('playing');
      startTick();
      startProgressSave();
    }
    highlightCurrentSentence();
  };

  if (switching) {
    if (canplayAbort) canplayAbort.abort();
    canplayAbort = new AbortController();
    state.audio.addEventListener('canplay', startPlay, { once: true, signal: canplayAbort.signal });
  } else {
    startPlay();
  }
}

function syncButtons() {
  btnPlay.classList.toggle('is-hidden', state.playing);
  btnPause.classList.toggle('is-hidden', !state.playing);
}

function startTick() {
  stopTick();
  state.tickInterval = setInterval(() => {
    if (state.playing && !state.audio.paused && !state.scrubbing) {
      const currentMs = state.audio.currentTime * 1000;
      const total = state.totalDurationMs || 1;
      if (state.currentItemId === state.playingItemId) {
        scrubber.value = Math.round((currentMs / total) * 10000);
        timeCurrent.textContent = formatTime(currentMs);
        highlightCurrentSentence();
      }
      }
  }, 100);
}

function stopTick() {
  if (state.tickInterval) {
    clearInterval(state.tickInterval);
    state.tickInterval = null;
  }
}

export function saveProgress() {
  const itemId = state.playingItemId;
  const src = state.audio.src;
  if (!itemId || !src) return;
  const currentSentence = getCurrentSentenceIndex();
  const currentTimeMs = state.audio.currentTime * 1000;
  api(`/api/library/${itemId}/progress`, {
    body: {
      current_sentence: currentSentence,
      current_time_ms: currentTimeMs,
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

export function prepareControls(item) {
  timeTotal.textContent = formatTime(item.total_duration_ms);
  statusText.textContent = item.title;
  const resumeMs = item.progress && !item.progress.is_finished ? item.progress.current_time_ms : 0;
  const total = item.total_duration_ms || 1;
  scrubber.value = Math.round((resumeMs / total) * 10000);
  timeCurrent.textContent = formatTime(resumeMs);
}
