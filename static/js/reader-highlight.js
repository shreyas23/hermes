import { state } from './state.js';

const container = document.getElementById('reader-content');
const followBtn = document.getElementById('btn-follow');

let autoFollow = true;
let userScrollTimeout = null;
let lastHighlightedIndex = -1;
let paragraphMap = [];

export function initReaderHighlight() {
  container.parentElement.addEventListener('scroll', () => {
    if (!state.playing) return;
    clearTimeout(userScrollTimeout);
    userScrollTimeout = setTimeout(() => {
      autoFollow = false;
      updateFollowButton();
    }, 50);
  }, { passive: true, capture: true });

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

export function renderContent(item) {
  container.innerHTML = '';
  paragraphMap = [];
  lastHighlightedIndex = -1;
  autoFollow = true;
  followBtn.classList.remove('is-visible');

  if (item.reader_html) {
    container.innerHTML = item.reader_html;
  } else {
    item.sentences.forEach(text => {
      const p = document.createElement('p');
      p.className = 'reader__paragraph';
      p.textContent = text;
      container.appendChild(p);
    });
  }

  buildParagraphMap(item.sentences);
}

function buildParagraphMap(sentences) {
  paragraphMap = [];

  const textEls = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_ELEMENT, {
    acceptNode: (node) => {
      const tag = node.tagName.toLowerCase();
      if (['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'pre', 'td', 'th'].includes(tag)) {
        return NodeFilter.FILTER_ACCEPT;
      }
      return NodeFilter.FILTER_SKIP;
    }
  });

  let node;
  while (node = walker.nextNode()) {
    const text = node.textContent.trim();
    if (text.length > 10) {
      textEls.push({ el: node, text });
    }
  }

  if (textEls.length === 0) return;

  for (let si = 0; si < sentences.length; si++) {
    const sentence = sentences[si];
    const words = sentence.split(/\s+/).slice(0, 6).join(' ').toLowerCase();
    if (words.length < 5) continue;

    let bestMatch = null;
    let bestScore = 0;

    for (let pi = 0; pi < textEls.length; pi++) {
      const pText = textEls[pi].text.toLowerCase();
      if (pText.includes(words)) {
        const score = words.length;
        if (score > bestScore) {
          bestScore = score;
          bestMatch = pi;
        }
      }
    }

    if (bestMatch !== null) {
      paragraphMap[si] = textEls[bestMatch].el;
    }
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
  container.querySelectorAll('.is-reading').forEach(el => el.classList.remove('is-reading'));
}

export function highlightCurrentSentence() {
  const index = getCurrentSentenceIndex();
  if (index === lastHighlightedIndex) return;
  lastHighlightedIndex = index;

  container.querySelectorAll('.is-reading').forEach(el => el.classList.remove('is-reading'));

  const el = paragraphMap[index];
  if (el) {
    el.classList.add('is-reading');
    if (autoFollow) scrollToActive();
    else updateFollowButton();
  }
}

function scrollToActive() {
  const el = container.querySelector('.is-reading');
  if (!el) return;

  const scrollParent = container;
  const containerRect = scrollParent.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const target = scrollParent.scrollTop + elRect.top - containerRect.top - containerRect.height / 3;

  autoFollow = true;
  scrollParent.scrollTo({ top: target, behavior: 'smooth' });
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
