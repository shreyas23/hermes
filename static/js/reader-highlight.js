import { state } from './state.js';

const container = document.getElementById('reader-content');
const followBtn = document.getElementById('btn-follow');
const tocBtn = document.getElementById('btn-toc');
const tocPanel = document.getElementById('reader-toc');
const readerView = document.getElementById('reader-view');
const teleprompterBtn = document.getElementById('btn-teleprompter');
const appEl = document.getElementById('app');

let autoFollow = true;
let programmaticScroll = false;
let userScrollTimeout = null;
let lastHighlightedIndex = -1;
let sentenceElements = [];
let selectedSentenceIndex = 0;
let teleprompterActive = false;

export function initReaderHighlight(onSentenceClick) {
  container.addEventListener('scroll', () => {
    if (!state.playing || programmaticScroll) return;
    clearTimeout(userScrollTimeout);
    userScrollTimeout = setTimeout(() => {
      autoFollow = false;
      updateFollowButton();
    }, 50);
  }, { passive: true });

  followBtn.addEventListener('click', () => {
    autoFollow = true;
    followBtn.classList.remove('is-visible');
    scrollToActive();
  });

  container.addEventListener('click', (e) => {
    const el = e.target.closest('[data-si]');
    if (!el) return;
    selectedSentenceIndex = parseInt(el.dataset.si);
    if (onSentenceClick) onSentenceClick(selectedSentenceIndex);
  });

  tocBtn.addEventListener('click', () => {
    const open = tocPanel.classList.toggle('is-hidden');
    readerView.classList.toggle('reader--toc-open', !open);
  });

  teleprompterBtn.addEventListener('click', toggleTeleprompter);
}

export function toggleTeleprompter() {
  teleprompterActive = !teleprompterActive;
  appEl.classList.toggle('app--teleprompter', teleprompterActive);
  teleprompterBtn.classList.toggle('is-active', teleprompterActive);
  autoFollow = true;
  followBtn.classList.remove('is-visible');
  lastHighlightedIndex = -1;
  highlightCurrentSentence();
  scrollToActive();
}

export function renderContent(item) {
  container.innerHTML = '';
  sentenceElements = [];
  lastHighlightedIndex = -1;
  selectedSentenceIndex = 0;
  autoFollow = true;
  followBtn.classList.remove('is-visible');

  if (item.reader_html) {
    container.innerHTML = item.reader_html;
  } else {
    item.sentences.forEach((text, i) => {
      const p = document.createElement('p');
      p.className = 'reader__paragraph';
      p.dataset.si = i;
      p.textContent = text;
      container.appendChild(p);
    });
  }

  container.querySelectorAll('[data-si]').forEach(el => {
    sentenceElements[parseInt(el.dataset.si)] = el;
  });

  if (item.toc && item.toc.length > 0) {
    tocBtn.classList.remove('is-hidden');
    tocPanel.innerHTML = '';
    const heading = document.createElement('div');
    heading.className = 'reader__toc-heading';
    heading.textContent = 'Contents';
    tocPanel.appendChild(heading);
    item.toc.forEach(entry => {
      const el = document.createElement('div');
      el.className = 'reader__toc-entry';
      el.dataset.level = entry.level;
      el.textContent = entry.title;
      if (entry.id) {
        el.addEventListener('click', () => {
          const target = container.querySelector(`#${entry.id}`);
          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            autoFollow = false;
          }
          tocPanel.classList.add('is-hidden');
          readerView.classList.remove('reader--toc-open');
        });
      }
      tocPanel.appendChild(el);
    });
  } else {
    tocBtn.classList.add('is-hidden');
    tocPanel.classList.add('is-hidden');
    readerView.classList.remove('reader--toc-open');
  }
}

export function getCurrentSentenceIndex() {
  if (!state.timeline.length) return -1;
  const currentMs = state.audio.currentTime * 1000;
  let lo = 0, hi = state.timeline.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (state.timeline[mid].start_ms <= currentMs) lo = mid + 1;
    else hi = mid - 1;
  }
  return Math.max(0, lo - 1);
}

export function clearHighlights() {
  lastHighlightedIndex = -1;
  container.querySelectorAll('.is-reading, .is-near, .is-played').forEach(el =>
    el.classList.remove('is-reading', 'is-near', 'is-played'));
}

// The passage a bookmark/annotation should target: the sentence being read when
// audio is loaded for this item, otherwise the last sentence the user clicked.
export function getActiveSentenceIndex() {
  if (state.currentItemId === state.playingItemId && state.timeline.length) {
    return getCurrentSentenceIndex();
  }
  return selectedSentenceIndex;
}

// Scroll a sentence into view and briefly flash it (used for bookmark jumps
// when there is no audio to seek).
export function scrollToSentence(index) {
  const el = sentenceElements[index];
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('is-flash');
  setTimeout(() => el.classList.remove('is-flash'), 1200);
}

export function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  if (index === lastHighlightedIndex) return;
  lastHighlightedIndex = index;

  container.querySelectorAll('.is-reading').forEach(el => el.classList.remove('is-reading'));

  if (teleprompterActive) {
    container.querySelectorAll('.is-near, .is-played').forEach(el =>
      el.classList.remove('is-near', 'is-played'));
    sentenceElements.forEach((el, i) => {
      if (!el) return;
      if (i < index) el.classList.add('is-played');
      else if (i !== index && Math.abs(i - index) <= 2) el.classList.add('is-near');
    });
  }

  const el = sentenceElements[index];
  if (el) {
    el.classList.add('is-reading');
    if (autoFollow) scrollToActive();
    else updateFollowButton();
  }
}

let rafId = null;
let rafFrom = 0;
let rafTo = 0;
let rafStart = 0;
const RAF_DURATION = 800;

function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

function animateScroll(to) {
  rafFrom = container.scrollTop;
  rafTo = to;
  rafStart = performance.now();
  programmaticScroll = true;
  if (rafId) cancelAnimationFrame(rafId);

  function step(now) {
    const t = Math.min((now - rafStart) / RAF_DURATION, 1);
    container.scrollTop = rafFrom + (rafTo - rafFrom) * easeOutCubic(t);
    if (t < 1) {
      rafId = requestAnimationFrame(step);
    } else {
      rafId = null;
      programmaticScroll = false;
    }
  }
  rafId = requestAnimationFrame(step);
}

function scrollToActive() {
  const el = container.querySelector('.is-reading');
  if (!el) return;

  const containerRect = container.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const offset = teleprompterActive ? containerRect.height / 2 - elRect.height / 2 : containerRect.height / 3;
  const target = container.scrollTop + elRect.top - containerRect.top - offset;

  autoFollow = true;

  if (teleprompterActive) {
    animateScroll(target);
  } else {
    programmaticScroll = true;
    container.scrollTo({ top: target, behavior: 'smooth' });
    setTimeout(() => { programmaticScroll = false; }, 500);
  }
}

function updateFollowButton() {
  const el = container.querySelector('.is-reading');
  if (!el || !state.playing) {
    followBtn.classList.remove('is-visible');
    return;
  }

  const containerRect = container.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const isVisible = elRect.top >= containerRect.top && elRect.bottom <= containerRect.bottom;

  if (isVisible) {
    autoFollow = true;
    followBtn.classList.remove('is-visible');
  } else {
    followBtn.classList.add('is-visible');
  }
}
