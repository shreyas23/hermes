// Bookmarks & annotations: mark the active passage, list them, jump to them,
// and attach a note (a bookmark with a note is an annotation).
import { api } from './api.js';
import { state } from './state.js';
import { getActiveSentenceIndex, scrollToSentence } from './reader-highlight.js';
import { escHtml } from './utils.js';

const btn = document.getElementById('btn-bookmarks');
const panel = document.getElementById('reader-bookmarks');
const listEl = document.getElementById('bookmark-list');

let onJump = null;

export function initBookmarks({ onJump: jump }) {
  onJump = jump;
  btn.addEventListener('click', togglePanel);
  document.getElementById('bookmark-add').addEventListener('click', addCurrent);
}

export async function loadBookmarks(itemId) {
  listEl.innerHTML = '';
  if (!itemId) return;
  const data = await api(`/api/library/${itemId}/bookmarks`, { showError: false });
  render(data.bookmarks || []);
}

export function resetBookmarks() {
  panel.classList.add('is-hidden');
  btn.classList.remove('is-active');
  listEl.innerHTML = '';
}

function togglePanel() {
  const open = panel.classList.toggle('is-hidden');
  btn.classList.toggle('is-active', !open);
}

export async function addCurrent() {
  const item = state.currentItem;
  if (!item) return;
  const idx = getActiveSentenceIndex();
  const quote = (item.sentences && item.sentences[idx]) || '';
  const data = await api(`/api/library/${item.id}/bookmarks`, { body: { sentence_index: idx, quote } });
  if (data.error) return;
  loadBookmarks(item.id);
}

function render(bookmarks) {
  listEl.innerHTML = '';
  if (!bookmarks.length) {
    listEl.innerHTML = '<div class="reader__bookmarks-empty">No bookmarks yet. Press “+ Add” to mark the current passage.</div>';
    return;
  }
  bookmarks.forEach(b => {
    const row = document.createElement('div');
    row.className = 'bookmark';
    row.innerHTML = `
      <div class="bookmark__quote" title="Jump to passage">${escHtml(b.quote || `Sentence ${b.sentence_index + 1}`)}</div>
      <input class="bookmark__note" placeholder="Add a note…" value="${escHtml(b.note || '')}">
      <button class="bookmark__delete" title="Delete">&times;</button>
    `;
    row.querySelector('.bookmark__quote').addEventListener('click', () => jumpTo(b.sentence_index));

    const noteInput = row.querySelector('.bookmark__note');
    let lastSaved = b.note || '';
    const saveNote = () => {
      if (noteInput.value === lastSaved) return;
      lastSaved = noteInput.value;
      api(`/api/bookmarks/${b.id}`, { method: 'PATCH', body: { note: noteInput.value } });
    };
    noteInput.addEventListener('change', saveNote);
    noteInput.addEventListener('blur', saveNote);
    noteInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); noteInput.blur(); } });

    row.querySelector('.bookmark__delete').addEventListener('click', async () => {
      await api(`/api/bookmarks/${b.id}`, { method: 'DELETE' });
      loadBookmarks(state.currentItemId);
    });
    listEl.appendChild(row);
  });
}

function jumpTo(index) {
  if (state.currentItem?.audio_ready && onJump) onJump(index);
  else scrollToSentence(index);
}
