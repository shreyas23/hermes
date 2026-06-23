import { api } from './api.js';
import { confirmAction } from './confirm-modal.js';
import { escHtml } from './utils.js';
import { toastError, toastSuccess } from './toast.js';

// Discovery is split into three layers so the modal can be promoted to a
// full main-area view later with no rewrite:
//   - data:      fetchWikipedia() / fetchFeedEntries() return plain item arrays
//   - rendering: renderResults(mount, items) is container-agnostic
//   - container: initDiscover() wires those into the modal shell

let onImport = null;

// --- Data (returns normalized {title, url, meta, snippet} items) ---

export async function fetchWikipedia(query) {
  if (!query) return [];
  const data = await api(`/api/discover/wikipedia?q=${encodeURIComponent(query)}`, { showError: false });
  if (data.error) { toastError(data.error); return []; }
  return (data.results || []).map(r => ({
    title: r.title,
    url: r.url,
    meta: r.description,
    snippet: r.snippet,
  }));
}

export async function fetchFeedEntries() {
  const data = await api('/api/feeds/entries', { showError: false });
  if (data.error) { toastError(data.error); return []; }
  return (data.entries || []).map(e => ({
    title: e.title,
    url: e.url,
    meta: [e.feed_title, e.published].filter(Boolean).join(' · '),
    snippet: e.summary,
  }));
}

// --- Rendering (container-agnostic) ---

export function renderResults(mount, items, emptyMsg) {
  mount.innerHTML = '';
  if (!items.length) {
    mount.innerHTML = `<div class="discover__empty">${escHtml(emptyMsg)}</div>`;
    return;
  }
  items.forEach(item => mount.appendChild(resultRow(item)));
}

function resultRow(item) {
  const row = document.createElement('div');
  row.className = 'discover__result';
  row.innerHTML = `
    <div class="discover__result-body">
      <div class="discover__result-title">${escHtml(item.title)}</div>
      ${item.meta ? `<div class="discover__result-meta">${escHtml(item.meta)}</div>` : ''}
      ${item.snippet ? `<div class="discover__result-snippet">${escHtml(item.snippet)}</div>` : ''}
    </div>
    <button class="discover__add">Add</button>
  `;
  const btn = row.querySelector('.discover__add');
  btn.addEventListener('click', () => addToLibrary(item.url, btn));
  return row;
}

function spinner(mount) {
  mount.innerHTML = '<div class="loading-overlay"><div class="spinner spinner--sm"></div></div>';
}

async function addToLibrary(url, btn) {
  if (!url) { toastError('No link available for this item'); return; }
  btn.disabled = true;
  btn.textContent = 'Adding…';

  let data = await api('/api/import/url', { body: { url }, showError: false });
  if (data.error === 'duplicate') {
    const title = data.existing?.title || 'an existing item';
    if (!await confirmAction({ title: 'Duplicate item', message: `Already in your library as "${title}". Add again?`, confirmLabel: 'Add anyway', destructive: false })) {
      btn.disabled = false; btn.textContent = 'Add';
      return;
    }
    data = await api('/api/import/url', { body: { url, force: true }, showError: false });
  }
  if (data.error) {
    toastError(data.error);
    btn.disabled = false; btn.textContent = 'Add';
    return;
  }

  btn.textContent = 'Added';
  btn.classList.add('is-done');
  onImport?.(data.item_id, false);
}

// --- Container (modal wiring) ---

export function initDiscover({ onImport: cb }) {
  onImport = cb;

  const backdrop = document.getElementById('discover-modal');
  document.getElementById('btn-discover').addEventListener('click', () => backdrop.classList.add('is-visible'));
  document.getElementById('discover-backdrop').addEventListener('click', () => backdrop.classList.remove('is-visible'));
  document.getElementById('discover-close').addEventListener('click', () => backdrop.classList.remove('is-visible'));
  document.getElementById('discover-done').addEventListener('click', () => backdrop.classList.remove('is-visible'));

  backdrop.querySelectorAll('.modal__tab').forEach(tab => {
    tab.addEventListener('click', () => selectTab(backdrop, tab.dataset.tab));
  });

  const searchInput = document.getElementById('discover-search-input');
  const runSearch = async () => {
    const mount = document.getElementById('discover-search-results');
    const query = searchInput.value.trim();
    if (!query) { mount.innerHTML = ''; return; }
    spinner(mount);
    renderResults(mount, await fetchWikipedia(query), `No results for “${query}”`);
  };
  document.getElementById('discover-search-btn').addEventListener('click', runSearch);
  searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });

  const feedInput = document.getElementById('discover-feed-input');
  const addFeed = () => subscribeFeed(feedInput);
  document.getElementById('discover-feed-add-btn').addEventListener('click', addFeed);
  feedInput.addEventListener('keydown', e => { if (e.key === 'Enter') addFeed(); });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && backdrop.classList.contains('is-visible')) {
      backdrop.classList.remove('is-visible');
    }
  });
}

function selectTab(backdrop, name) {
  backdrop.querySelectorAll('.modal__tab').forEach(t => t.classList.toggle('is-active', t.dataset.tab === name));
  backdrop.querySelectorAll('.modal__pane').forEach(p => p.classList.toggle('is-active', p.id === `discover-pane-${name}`));
  if (name === 'feeds') refreshFeeds();
}

async function refreshFeeds() {
  await loadFeedList();
  const mount = document.getElementById('discover-feed-entries');
  spinner(mount);
  renderResults(mount, await fetchFeedEntries(), 'No recent entries from your feeds');
}

async function loadFeedList() {
  const mount = document.getElementById('discover-feed-list');
  const data = await api('/api/feeds', { showError: false });
  const feeds = data.feeds || [];
  mount.innerHTML = '';
  if (!feeds.length) {
    mount.innerHTML = '<div class="discover__empty">No subscriptions yet — add an RSS or Substack feed above.</div>';
    return;
  }
  feeds.forEach(f => {
    const chip = document.createElement('div');
    chip.className = 'discover__feed';
    chip.innerHTML = `<span class="discover__feed-title">${escHtml(f.title)}</span><button class="discover__feed-remove" title="Unsubscribe">&times;</button>`;
    chip.querySelector('.discover__feed-remove').addEventListener('click', async () => {
      await api(`/api/feeds/${f.id}`, { method: 'DELETE' });
      refreshFeeds();
    });
    mount.appendChild(chip);
  });
}

async function subscribeFeed(input) {
  const url = input.value.trim();
  if (!url) return;
  const btn = document.getElementById('discover-feed-add-btn');
  btn.disabled = true;
  btn.textContent = 'Adding…';
  const data = await api('/api/feeds', { body: { url }, showError: false });
  btn.disabled = false;
  btn.textContent = 'Subscribe';
  if (data.error) {
    toastError(data.error === 'Already subscribed' ? 'Already subscribed to that feed' : data.error);
    return;
  }
  input.value = '';
  toastSuccess(`Subscribed to ${data.title}`);
  refreshFeeds();
}
