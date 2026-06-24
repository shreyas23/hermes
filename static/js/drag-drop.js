// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

import { toastSuccess, toastError } from './toast.js';

const SUPPORTED = new Set(['.pdf', '.docx', '.md', '.txt', '.rtf', '.html', '.htm']);

let onImported = null;
const overlay = document.getElementById('drop-overlay');
let dragCounter = 0;

export function initDragDrop({ onImport }) {
  onImported = onImport;

  document.addEventListener('dragenter', e => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) overlay.classList.add('is-visible');
  });

  document.addEventListener('dragleave', () => {
    dragCounter--;
    if (dragCounter === 0) overlay.classList.remove('is-visible');
  });

  document.addEventListener('dragover', e => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  document.addEventListener('drop', async e => {
    e.preventDefault();
    dragCounter = 0;
    overlay.classList.remove('is-visible');

    const files = [...e.dataTransfer.files].filter(f => {
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      return SUPPORTED.has(ext);
    });
    if (files.length === 0) return;

    let firstId = null;
    let count = 0;

    for (const file of files) {
      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch('/api/import/upload', { method: 'POST', body: form });
        const data = await res.json();
        if (data.error) {
          toastError(`${file.name}: ${data.error}`);
          continue;
        }
        count++;
        if (!firstId) firstId = data.item_id;
      } catch {
        toastError(`Failed to import ${file.name}`);
      }
    }

    if (count > 0) {
      toastSuccess(`Imported ${count} file${count > 1 ? 's' : ''}`);
      onImported?.(firstId);
    }
  });
}
