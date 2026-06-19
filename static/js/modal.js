import { api } from './api.js';
import { toastSuccess } from './toast.js';
import { escHtml } from './utils.js';

const backdrop = document.getElementById('import-modal');
let onImported = null;

export function initModal({ onImport }) {
  onImported = onImport;

  document.getElementById('btn-add').addEventListener('click', open);
  document.getElementById('import-backdrop').addEventListener('click', close);
  document.getElementById('import-close').addEventListener('click', close);

  document.querySelectorAll('.modal__tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.modal__tab').forEach(t => t.classList.remove('is-active'));
      document.querySelectorAll('.modal__pane').forEach(p => p.classList.remove('is-active'));
      tab.classList.add('is-active');
      document.getElementById(`pane-${tab.dataset.tab}`).classList.add('is-active');
    });
  });

  document.getElementById('import-url-btn').addEventListener('click', importUrl);
  document.getElementById('import-file-btn').addEventListener('click', importFile);
  document.getElementById('import-folder-scan-btn').addEventListener('click', scanFolder);
  document.getElementById('import-text-btn').addEventListener('click', importText);

  document.addEventListener('keydown', e => {
    if (e.code === 'Escape' && backdrop.classList.contains('is-visible')) {
      close();
    }
  });
}

function open() {
  backdrop.classList.add('is-visible');
}

function close() {
  backdrop.classList.remove('is-visible');
}

async function importUrl() {
  const url = document.getElementById('import-url').value.trim();
  if (!url) return;
  const btn = document.getElementById('import-url-btn');
  btn.textContent = 'Importing...';
  btn.disabled = true;
  const data = await api('/api/import/url', { body: { url } });
  btn.textContent = 'Import Article';
  btn.disabled = false;
  if (data.error) return;
  document.getElementById('import-url').value = '';
  close();
  onImported?.(data.item_id);
}

async function importFile() {
  const path = document.getElementById('import-file-path').value.trim();
  if (!path) return;
  const data = await api('/api/import/file', { body: { path } });
  if (data.error) return;
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
      const res = await api('/api/import/file', { body: { path: f.path } });
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
