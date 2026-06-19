import { state } from './state.js';

const container = document.getElementById('sentences-container');
const followBtn = document.getElementById('btn-follow');

let onSentenceClick = null;
let autoFollow = true;
let userScrollTimeout = null;
let lastHighlightedIndex = -1;

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
  for (let i = state.timeline.length - 1; i >= 0; i--) {
    if (currentMs >= state.timeline[i].start_ms) return i;
  }
  return 0;
}

export function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  if (index === lastHighlightedIndex) return;
  lastHighlightedIndex = index;

  const els = container.querySelectorAll('.sentence');
  els.forEach((el, i) => {
    el.classList.toggle('is-active', i === index);
    el.classList.toggle('is-near', i !== index && Math.abs(i - index) <= 2);
    el.classList.toggle('is-played', i < index && Math.abs(i - index) > 2);
  });

  if (autoFollow) {
    scrollToActive();
  } else {
    updateFollowButton();
  }
}

function scrollToActive() {
  const activeEl = container.querySelector('.sentence.is-active');
  if (!activeEl) return;

  const containerRect = container.getBoundingClientRect();
  const elRect = activeEl.getBoundingClientRect();
  const target = container.scrollTop + elRect.top - containerRect.top - containerRect.height / 2 + elRect.height / 2;

  autoFollow = true;
  container.scrollTo({ top: target, behavior: 'smooth' });
}

function updateFollowButton() {
  const activeEl = container.querySelector('.sentence.is-active');
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
