import { state } from './state.js';

const container = document.getElementById('reader-content');
const followBtn = document.getElementById('btn-follow');

let autoFollow = true;
let userScrollTimeout = null;
let lastHighlightedIndex = -1;
let sentenceElements = [];

export function initReaderHighlight(onSentenceClick) {
  container.addEventListener('scroll', () => {
    if (!state.playing) return;
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

  if (onSentenceClick) {
    container.addEventListener('click', (e) => {
      const el = e.target.closest('[data-si]');
      if (el) onSentenceClick(parseInt(el.dataset.si));
    });
  }
}

export function renderContent(item) {
  container.innerHTML = '';
  sentenceElements = [];
  lastHighlightedIndex = -1;
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
  container.querySelectorAll('.is-reading').forEach(el => el.classList.remove('is-reading'));
}

export function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  if (index === lastHighlightedIndex) return;
  lastHighlightedIndex = index;

  container.querySelectorAll('.is-reading').forEach(el => el.classList.remove('is-reading'));

  const el = sentenceElements[index];
  if (el) {
    el.classList.add('is-reading');
    if (autoFollow) scrollToActive();
    else updateFollowButton();
  }
}

function scrollToActive() {
  const el = container.querySelector('.is-reading');
  if (!el) return;

  const containerRect = container.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const target = container.scrollTop + elRect.top - containerRect.top - containerRect.height / 3;

  autoFollow = true;
  container.scrollTo({ top: target, behavior: 'smooth' });
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
