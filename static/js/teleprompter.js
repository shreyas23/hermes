import { state } from './state.js';

const container = document.getElementById('sentences-container');
const followBtn = document.getElementById('btn-follow');

let onSentenceClick = null;
let autoFollow = true;
let userScrollTimeout = null;
let lastHighlightedIndex = -1;
let sentenceEls = [];

export function initTeleprompter({ onClick }) {
  onSentenceClick = onClick;

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
}

export function renderSentences(sentences, images = [], itemId = null) {
  container.innerHTML = '';
  sentenceEls = [];
  autoFollow = true;
  lastHighlightedIndex = -1;
  followBtn.classList.remove('is-visible');

  const imagesByPosition = {};
  if (images) {
    images.forEach(img => {
      const pos = img.after_sentence;
      if (!imagesByPosition[pos]) imagesByPosition[pos] = [];
      imagesByPosition[pos].push(img);
    });
  }

  sentences.forEach((text, i) => {
    const el = document.createElement('div');
    el.className = 'sentence';
    el.dataset.index = i;
    el.textContent = text;
    el.addEventListener('click', () => onSentenceClick?.(i));
    sentenceEls.push(el);
    container.appendChild(el);

    if (imagesByPosition[i] && itemId) {
      imagesByPosition[i].forEach(img => {
        const wrapper = document.createElement('div');
        wrapper.className = 'teleprompter__image';
        const imgEl = document.createElement('img');
        imgEl.src = `/api/library/${itemId}/images/${img.filename}`;
        imgEl.alt = img.alt || '';
        imgEl.loading = 'lazy';
        wrapper.appendChild(imgEl);
        if (img.alt) {
          const caption = document.createElement('div');
          caption.className = 'teleprompter__image-caption';
          caption.textContent = img.alt;
          wrapper.appendChild(caption);
        }
        container.appendChild(wrapper);
      });
    }
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
  for (const el of sentenceEls) {
    el.classList.remove('is-active', 'is-near', 'is-played');
  }
}

export function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  if (index === lastHighlightedIndex) return;
  const prev = lastHighlightedIndex;
  lastHighlightedIndex = index;

  const els = sentenceEls;
  if (!els.length) return;

  const updateRange = (from, to) => {
    const lo = Math.max(0, Math.min(from, to) - 3);
    const hi = Math.min(els.length - 1, Math.max(from, to) + 3);
    for (let i = lo; i <= hi; i++) {
      els[i].classList.toggle('is-active', i === index);
      els[i].classList.toggle('is-near', i !== index && Math.abs(i - index) <= 2);
      els[i].classList.toggle('is-played', i < index && Math.abs(i - index) > 2);
    }
  };

  if (prev === -1) {
    for (let i = 0; i < els.length; i++) {
      els[i].classList.toggle('is-active', i === index);
      els[i].classList.toggle('is-near', i !== index && Math.abs(i - index) <= 2);
      els[i].classList.toggle('is-played', i < index && Math.abs(i - index) > 2);
    }
  } else {
    updateRange(prev, index);
  }

  if (autoFollow) {
    scrollToActive();
  } else {
    updateFollowButton();
  }
}

function scrollToActive() {
  const activeEl = lastHighlightedIndex >= 0 ? sentenceEls[lastHighlightedIndex] : null;
  if (!activeEl) return;

  const containerRect = container.getBoundingClientRect();
  const elRect = activeEl.getBoundingClientRect();
  const target = container.scrollTop + elRect.top - containerRect.top - containerRect.height / 2 + elRect.height / 2;

  autoFollow = true;
  container.scrollTo({ top: target, behavior: 'smooth' });
}

function updateFollowButton() {
  const activeEl = lastHighlightedIndex >= 0 ? sentenceEls[lastHighlightedIndex] : null;
  if (!activeEl || !state.playing) {
    followBtn.classList.remove('is-visible');
    return;
  }

  const containerRect = container.getBoundingClientRect();
  const elRect = activeEl.getBoundingClientRect();
  const isVisible = elRect.top >= containerRect.top && elRect.bottom <= containerRect.bottom;

  if (isVisible) {
    autoFollow = true;
    followBtn.classList.remove('is-visible');
  } else {
    followBtn.classList.add('is-visible');
  }
}
