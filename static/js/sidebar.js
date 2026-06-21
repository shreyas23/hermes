import { api } from './api.js';
import { state } from './state.js';
import { showContextMenu } from './contextmenu.js';
import { confirmAction } from './confirm-modal.js';
import { toastSuccess } from './toast.js';
import { formatTime, escHtml } from './utils.js';

const itemList = document.getElementById('item-list');
const collectionsList = document.getElementById('collections-list');
const searchInput = document.getElementById('search-input');

let onItemOpen = null;
let onItemDelete = null;
let searchTimeout = null;

export function initSidebar({ onOpen, onDelete }) {
  onItemOpen = onOpen;
  onItemDelete = onDelete;

  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const query = searchInput.value.trim();
    if (!query) {
      loadView(state.currentView);
      return;
    }
    searchTimeout = setTimeout(async () => {
      const data = await api(`/api/library/search?q=${encodeURIComponent(query)}`, { showError: false });
      if (data.items) renderItemList(data.items);
    }, 250);
  });

  document.querySelectorAll('.nav__item').forEach(el => {
    el.addEventListener('click', () => {
      setActiveNav(el);
      state.currentView = el.dataset.view;
      loadView(el.dataset.view);
    });
  });

  document.getElementById('btn-new-collection').addEventListener('click', async () => {
    const name = prompt('Collection name:');
    if (!name) return;
    await api('/api/collections', { body: { name } });
    loadCollections();
  });
}

function setActiveNav(el) {
  document.querySelectorAll('.nav__item, .nav__collection').forEach(e => e.classList.remove('is-active'));
  el.classList.add('is-active');
}

export async function loadView(view) {
  let params;
  switch (view) {
    case 'recent': params = '?view=recent'; break;
    case 'in_progress': params = '?view=in_progress'; break;
    case 'articles': params = '?source_type=article'; break;
    case 'documents': params = '?source_type=document'; break;
    case 'texts': params = '?source_type=text'; break;
    default: params = ''; break;
  }
  itemList.innerHTML = '<div class="loading-overlay"><div class="spinner spinner--sm"></div></div>';
  const data = await api(`/api/library${params}`);
  if (data.items) renderItemList(data.items);
}

async function loadCollection(id) {
  itemList.innerHTML = '<div class="loading-overlay"><div class="spinner spinner--sm"></div></div>';
  const data = await api(`/api/library?view=collection&collection_id=${id}`);
  if (data.items) renderItemList(data.items);
}

const emptyMessages = {
  recent: 'No items yet — click + to import',
  in_progress: 'Nothing in progress',
  articles: 'No articles — import a URL to get started',
  documents: 'No documents — import a file to get started',
  texts: 'No text items yet',
};

function renderItemList(items) {
  itemList.innerHTML = '';
  if (items.length === 0) {
    const msg = emptyMessages[state.currentView] || 'No items yet';
    itemList.innerHTML = `<div class="item-list__empty">${msg}</div>`;
    return;
  }
  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'item' + (item.id === state.currentItemId ? ' is-active' : '');

    const dur = item.audio_ready ? formatTime(item.total_duration_ms) : '';
    let badge = '';
    if (!item.audio_ready) {
      if (item.generating) badge = '<span class="badge badge--generating">generating</span>';
      else if (item.interrupted) badge = '<span class="badge badge--interrupted">interrupted</span>';
      else badge = '<span class="badge badge--pending">no audio</span>';
    }
    let progress = '';
    if (item.audio_ready && item.progress && item.progress.current_time_ms > 0 && !item.progress.is_finished && item.total_duration_ms > 0) {
      const pct = Math.round((item.progress.current_time_ms / item.total_duration_ms) * 100);
      progress = `<div class="item__progress"><div class="item__progress-fill" style="width:${pct}%"></div></div>`;
    }

    const genBar = item.generating
      ? `<div class="item__progress item__progress--gen" data-gen-id="${item.id}"><div class="item__progress-fill" style="width:0%"></div></div>`
      : '';

    el.innerHTML = `
      <div class="item__body">
        <div class="item__title">${escHtml(item.title)}</div>
        <div class="item__meta">
          <span>${item.source_type}</span>
          ${dur ? `<span>${dur}</span>` : ''}
          ${badge}
        </div>
        ${progress}
        ${genBar}
      </div>
      <button class="item__delete" title="Delete">&times;</button>
    `;

    el.addEventListener('click', () => onItemOpen?.(item.id));
    el.addEventListener('contextmenu', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const actions = [
        { label: 'Open', onClick: () => onItemOpen?.(item.id) },
      ];
      if (!item.audio_ready && !item.generating) {
        actions.push({
          label: item.interrupted ? 'Regenerate audio' : 'Generate audio',
          onClick: async () => {
            const data = await api(`/api/library/${item.id}/generate`, { method: 'POST' });
            if (data.error) return;
            loadView(state.currentView);
          },
        });
      }
      actions.push({ separator: true });
      const data = await api('/api/collections', { showError: false });
      if (data.collections?.length) {
        data.collections.forEach(c => {
          actions.push({
            label: `Add to ${c.name}`,
            onClick: async () => {
              await api(`/api/collections/${c.id}/items`, { body: { item_id: item.id } });
              toastSuccess(`Added to ${c.name}`);
              loadCollections();
            },
          });
        });
        actions.push({ separator: true });
      }
      actions.push({
        label: 'Delete',
        destructive: true,
        onClick: async () => {
          if (!await confirmAction({ title: 'Delete item?', message: `"${item.title}" will be permanently removed from your library.`, confirmLabel: 'Delete' })) return;
          await api(`/api/library/${item.id}`, { method: 'DELETE' });
          onItemDelete?.(item.id);
          loadView(state.currentView);
          loadCollections();
        },
      });
      showContextMenu(e, actions);
    });
    el.querySelector('.item__delete').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!await confirmAction({ title: 'Delete item?', message: `"${item.title}" will be permanently removed from your library.`, confirmLabel: 'Delete' })) return;
      await api(`/api/library/${item.id}`, { method: 'DELETE' });
      onItemDelete?.(item.id);
      loadView(state.currentView);
      loadCollections();
    });

    itemList.appendChild(el);
  });
}

export function updateGenerationProgress(itemId, pct) {
  const bar = itemList.querySelector(`[data-gen-id="${itemId}"] .item__progress-fill`);
  if (bar) bar.style.width = `${pct}%`;
}

export async function loadCollections() {
  const data = await api('/api/collections');
  if (!data.collections) return;
  collectionsList.innerHTML = '';
  data.collections.forEach(c => {
    const el = document.createElement('div');
    el.className = 'nav__collection';
    el.textContent = `${c.name} (${c.count})`;
    el.addEventListener('click', () => {
      setActiveNav(el);
      loadCollection(c.id);
    });
    collectionsList.appendChild(el);
  });
}
