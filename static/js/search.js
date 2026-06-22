// Find-in-transcript: highlights matches in the reader and steps through them.
// Pure frontend, operates on #reader-content text nodes (wraps matches in <mark>).

const container = document.getElementById('reader-content');
const bar = document.getElementById('reader-search');
const input = document.getElementById('reader-search-input');
const countEl = document.getElementById('reader-search-count');
const playerState = document.getElementById('player-state');

let hits = [];
let current = -1;

export function initSearch() {
  document.getElementById('btn-search').addEventListener('click', toggle);
  document.getElementById('reader-search-close').addEventListener('click', close);
  document.getElementById('reader-search-next').addEventListener('click', () => step(1));
  document.getElementById('reader-search-prev').addEventListener('click', () => step(-1));

  let debounce;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => run(input.value), 150);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  });

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f') {
      if (!playerState.classList.contains('is-visible')) return;
      e.preventDefault();
      open();
    }
  });
}

// Called when the reader content changes (new item opened) so stale state resets.
export function resetSearch() {
  hits = [];
  current = -1;
  countEl.textContent = '';
  bar.classList.add('is-hidden');
  input.value = '';
}

function clearMarks() {
  for (const mark of hits) {
    const parent = mark.parentNode;
    if (!parent) continue;
    parent.replaceChild(document.createTextNode(mark.textContent), mark);
    parent.normalize();
  }
  hits = [];
  current = -1;
}

function toggle() {
  bar.classList.contains('is-hidden') ? open() : close();
}

function open() {
  bar.classList.remove('is-hidden');
  input.focus();
  input.select();
  if (input.value.trim()) run(input.value);
}

function close() {
  bar.classList.add('is-hidden');
  clearMarks();
  countEl.textContent = '';
}

function run(query) {
  clearMarks();
  query = query.trim();
  if (query.length < 2) { countEl.textContent = ''; return; }
  const lower = query.toLowerCase();

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode: n => n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
  });
  const textNodes = [];
  let n;
  while ((n = walker.nextNode())) textNodes.push(n);

  for (const node of textNodes) {
    const text = node.nodeValue;
    const haystack = text.toLowerCase();
    const starts = [];
    let i = haystack.indexOf(lower);
    while (i !== -1) { starts.push(i); i = haystack.indexOf(lower, i + lower.length); }
    if (!starts.length) continue;

    const frag = document.createDocumentFragment();
    let pos = 0;
    for (const start of starts) {
      if (start > pos) frag.appendChild(document.createTextNode(text.slice(pos, start)));
      const mark = document.createElement('mark');
      mark.className = 'search-hit';
      mark.textContent = text.slice(start, start + query.length);
      frag.appendChild(mark);
      hits.push(mark);
      pos = start + query.length;
    }
    if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
    node.parentNode.replaceChild(frag, node);
  }

  if (hits.length) { current = 0; focusCurrent(); }
  updateCount();
}

function step(dir) {
  if (!hits.length) return;
  current = (current + dir + hits.length) % hits.length;
  focusCurrent();
}

function focusCurrent() {
  hits.forEach((m, i) => m.classList.toggle('is-current', i === current));
  hits[current]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  updateCount();
}

function updateCount() {
  countEl.textContent = hits.length ? `${current + 1}/${hits.length}` : 'No results';
}
