import { api } from './api.js';
import { state, SPEED_OPTIONS } from './state.js';
import { highlightCurrentSentence, getCurrentSentenceIndex, clearHighlights } from './reader-highlight.js';
import { formatTime } from './utils.js';

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
const miniPlayer = document.getElementById('mini-player');
const miniTitle = document.getElementById('mini-title');
const miniTime = document.getElementById('mini-time');
const miniPlay = document.getElementById('mini-play');
const miniPause = document.getElementById('mini-pause');
const miniProgressFill = document.getElementById('mini-progress-fill');
let canplayAbort = null;

export function initPlayer() {
  btnPlay.addEventListener('click', play);
  btnPause.addEventListener('click', pause);

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

  btnSpeed.addEventListener('click', () => {
    state.speedIndex = (state.speedIndex + 1) % SPEED_OPTIONS.length;
    const speed = SPEED_OPTIONS[state.speedIndex];
    state.audio.playbackRate = speed;
    btnSpeed.textContent = speed === 1 ? '1x' : `${speed}x`;
  });

  state.audio.addEventListener('ended', () => {
    state.playing = false;
    syncButtons();
    stopTick();
    stopProgressSave();
    if (state.currentItemId) {
      api(`/api/library/${state.currentItemId}/progress`, {
        body: { current_sentence: state.timeline.length, current_time_ms: 0, is_finished: true }
      });
    }
    updateMiniPlayer();
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

  // Mini player
  miniPlay.addEventListener('click', (e) => { e.stopPropagation(); play(); });
  miniPause.addEventListener('click', (e) => { e.stopPropagation(); pause(); });

  // Keyboard
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    switch (e.code) {
      case 'Space':
        if (!state.currentItem?.audio_ready) return;
        e.preventDefault();
        state.playing ? pause() : play();
        break;
      case 'ArrowLeft': e.preventDefault(); btnPrev.click(); break;
      case 'ArrowRight': e.preventDefault(); btnNext.click(); break;
    }
  });

  window.addEventListener('beforeunload', saveProgress);
}

export function loadAudio(item) {
  if (canplayAbort) canplayAbort.abort();

  timeTotal.textContent = formatTime(item.total_duration_ms);
  timeCurrent.textContent = '0:00';
  scrubber.value = 0;
  statusText.textContent = item.title;
  state.audio.src = `/api/library/${item.id}/audio`;
  state.audio.playbackRate = SPEED_OPTIONS[state.speedIndex];
  state.audio.load();

  if (item.progress && item.progress.current_time_ms > 0 && !item.progress.is_finished) {
    const resumeMs = item.progress.current_time_ms;
    canplayAbort = new AbortController();
    state.audio.addEventListener('canplay', () => {
      state.audio.currentTime = resumeMs / 1000;
      highlightCurrentSentence();
    }, { once: true, signal: canplayAbort.signal });
  }

  updateMiniPlayer();
}

export function play() {
  if (!state.currentItem || !state.currentItem.audio_ready) return;
  state.audio.play();
  state.playing = true;
  syncButtons();
  startTick();
  startProgressSave();
  updateMiniPlayer();
}

export function pause() {
  state.audio.pause();
  state.playing = false;
  syncButtons();
  stopTick();
  stopProgressSave();
  saveProgress();
  updateMiniPlayer();
}

export function stop() {
  state.audio.pause();
  state.audio.currentTime = 0;
  state.playing = false;
  syncButtons();
  stopTick();
  stopProgressSave();
  scrubber.value = 0;
  timeCurrent.textContent = '0:00';
  clearHighlights();
}

export function seekToSentence(index) {
  if (!state.timeline[index]) return;
  state.audio.currentTime = state.timeline[index].start_ms / 1000;
  if (!state.playing) {
    state.audio.play();
    state.playing = true;
    syncButtons();
    startTick();
  }
  highlightCurrentSentence();
}

function syncButtons() {
  btnPlay.classList.toggle('is-hidden', state.playing);
  btnPause.classList.toggle('is-hidden', !state.playing);
  miniPlay.classList.toggle('is-hidden', state.playing);
  miniPause.classList.toggle('is-hidden', !state.playing);
}

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

export function saveProgress() {
  const itemId = state.currentItemId;
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

function updateMiniPlayer() {
  if (!state.currentItem) {
    miniPlayer.classList.remove('is-visible');
    document.querySelector('.app').classList.remove('has-mini-player');
    return;
  }
  miniPlayer.classList.add('is-visible');
  document.querySelector('.app').classList.add('has-mini-player');
  miniTitle.textContent = state.currentItem.title;
  const currentMs = state.audio.currentTime * 1000;
  const total = state.totalDurationMs || 1;
  miniTime.textContent = `${formatTime(currentMs)} / ${formatTime(total)}`;
  miniProgressFill.style.width = `${(currentMs / total) * 100}%`;
}
