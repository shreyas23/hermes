import { api } from './api.js';
import { toastSuccess, toastError } from './toast.js';
import { escHtml } from './utils.js';

const backdrop = document.getElementById('import-modal');
let onImported = null;

export function initModal({ onImport }) {
  onImported = onImport;

  document.getElementById('btn-add').addEventListener('click', open);
  document.getElementById('import-backdrop').addEventListener('click', close);
  document.getElementById('import-close').addEventListener('click', close);

  // Scope tab wiring to the import modal — the Discover modal reuses .modal__tab
  // and handles its own tabs in discover.js.
  backdrop.querySelectorAll('.modal__tab').forEach(tab => {
    tab.addEventListener('click', () => {
      backdrop.querySelectorAll('.modal__tab').forEach(t => t.classList.remove('is-active'));
      backdrop.querySelectorAll('.modal__pane').forEach(p => p.classList.remove('is-active'));
      tab.classList.add('is-active');
      document.getElementById(`pane-${tab.dataset.tab}`).classList.add('is-active');
    });
  });

  document.getElementById('import-url-btn').addEventListener('click', importUrl);
  document.getElementById('import-file-btn').addEventListener('click', importFile);
  document.getElementById('import-folder-scan-btn').addEventListener('click', scanFolder);
  document.getElementById('import-text-btn').addEventListener('click', importText);

  document.getElementById('watch-folder-add-btn').addEventListener('click', addWatchFolder);

  document.addEventListener('keydown', e => {
    if (e.code === 'Escape') {
      if (backdrop.classList.contains('is-visible')) close();
      const settingsModal = document.getElementById('settings-modal');
      if (settingsModal?.classList.contains('is-visible')) settingsModal.classList.remove('is-visible');
    }
  });
}

function open() {
  backdrop.classList.add('is-visible');
  loadWatchFolders();
}

function close() {
  backdrop.classList.remove('is-visible');
}

async function importWithDuplicateCheck(path, body) {
  let data = await api(path, { body, showError: false });
  if (data.error === 'duplicate') {
    const title = data.existing?.title || 'an existing item';
    if (!confirm(`This item already exists as "${title}". Import anyway?`)) return null;
    data = await api(path, { body: { ...body, force: true } });
  } else if (data.error) {
    toastError(data.error);
  }
  return data;
}

async function importUrl() {
  const url = document.getElementById('import-url').value.trim();
  if (!url) return;
  const btn = document.getElementById('import-url-btn');
  btn.textContent = 'Importing...';
  btn.disabled = true;
  const data = await importWithDuplicateCheck('/api/import/url', { url });
  btn.textContent = 'Import Article';
  btn.disabled = false;
  if (!data || data.error) return;
  document.getElementById('import-url').value = '';
  close();
  onImported?.(data.item_id);
}

async function importFile() {
  const path = document.getElementById('import-file-path').value.trim();
  if (!path) return;
  const data = await importWithDuplicateCheck('/api/import/file', { path });
  if (!data || data.error) return;
  document.getElementById('import-file-path').value = '';
  close();
  onImported?.(data.item_id);
}

async function scanFolder() {
  const folder = document.getElementById('import-folder-path').value.trim();
  if (!folder) return;
  const data = await api('/api/import/folder', { body: { folder } });
  if (data.error) return;
  const results = document.getElementById('folder-scan-results');
  results.innerHTML = '';
  data.files.forEach(f => {
    const el = document.createElement('div');
    el.className = 'folder-results__file';
    el.innerHTML = `<span>${escHtml(f.name)}</span><button class="folder-results__import">Import</button>`;
    el.querySelector('button').addEventListener('click', async (e) => {
      const btn = e.target;
      btn.textContent = '...';
      const res = await importWithDuplicateCheck('/api/import/file', { path: f.path });
      if (!res) { btn.textContent = 'Import'; return; }
      if (res.error) { btn.textContent = 'Error'; return; }
      btn.textContent = 'Done';
      btn.classList.add('is-done');
      onImported?.(res.item_id, false);
    });
    results.appendChild(el);
  });
}

async function importText() {
  const title = document.getElementById('import-text-title').value.trim() || 'Untitled';
  const text = document.getElementById('import-text-content').value.trim();
  if (!text) return;
  const data = await api('/api/import/text', { body: { title, text } });
  if (data.error) return;
  document.getElementById('import-text-title').value = '';
  document.getElementById('import-text-content').value = '';
  close();
  onImported?.(data.item_id);
}

async function loadWatchFolders() {
  const list = document.getElementById('watch-folders-list');
  const data = await api('/api/watch-folders', { showError: false });
  if (!data.folders) return;
  list.innerHTML = '';
  if (data.folders.length === 0) {
    list.innerHTML = '<div class="watch-folders__empty">No watch folders</div>';
    return;
  }
  data.folders.forEach(f => {
    const el = document.createElement('div');
    el.className = 'watch-folder';
    el.innerHTML = `
      <span class="watch-folder__path">${escHtml(f.path)}</span>
      <button class="watch-folder__remove" title="Remove">&times;</button>
    `;
    el.querySelector('.watch-folder__remove').addEventListener('click', async () => {
      await api(`/api/watch-folders/${f.id}`, { method: 'DELETE' });
      loadWatchFolders();
    });
    list.appendChild(el);
  });
}

async function addWatchFolder() {
  const input = document.getElementById('import-folder-path');
  const path = input.value.trim();
  if (!path) return;
  const data = await api('/api/watch-folders', { body: { path }, showError: false });
  if (data.error) {
    toastError(data.error);
    return;
  }
  loadWatchFolders();
}
