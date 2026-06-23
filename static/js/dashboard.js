import { api } from './api.js';
import { escHtml, formatTime, timeAgo } from './utils.js';

const dashboard = document.getElementById('dashboard');
const emptyText = document.getElementById('empty-state-text');
const continueSection = document.getElementById('dash-continue');
const continueItems = document.getElementById('dash-continue-items');
const recentItems = document.getElementById('dash-recent-items');
const statsRow = document.getElementById('dash-stats-row');

let onOpen = null;

export function initDashboard({ onOpen: openFn }) {
  onOpen = openFn;
}

export async function loadDashboard() {
  const [inProgress, recent, stats] = await Promise.all([
    api('/api/library?view=in_progress', { showError: false }),
    api('/api/library?view=recent', { showError: false }),
    api('/api/stats', { showError: false }),
  ]);

  if (!stats || stats.items === 0) {
    dashboard.classList.add('is-hidden');
    emptyText.classList.remove('is-hidden');
    return;
  }

  dashboard.classList.remove('is-hidden');
  emptyText.classList.add('is-hidden');

  const ipItems = inProgress?.items || [];
  if (ipItems.length > 0) {
    continueSection.classList.remove('is-hidden');
    continueItems.innerHTML = ipItems.map(item => continueCard(item)).join('');
  } else {
    continueSection.classList.add('is-hidden');
  }

  const recItems = (recent?.items || []).slice(0, 8);
  recentItems.innerHTML = recItems.map(item => recentCard(item)).join('');

  statsRow.innerHTML = [
    stat(stats.items, 'items'),
    stat(formatTime(stats.total_duration_ms), 'listening'),
    stat(stats.bookmarks, 'bookmarks'),
    stat(stats.feeds, 'feeds'),
  ].join('');

  dashboard.querySelectorAll('[data-item-id]').forEach(card => {
    card.addEventListener('click', () => onOpen?.(Number(card.dataset.itemId)));
  });
}

function continueCard(item) {
  const p = item.progress || {};
  const pct = item.total_duration_ms > 0
    ? Math.round((p.current_time_ms || 0) / item.total_duration_ms * 100)
    : 0;
  const dur = item.total_duration_ms > 0 ? formatTime(item.total_duration_ms) : '';
  const ago = p.last_played_at ? timeAgo(p.last_played_at) : '';

  return `<div class="dashboard__card" data-item-id="${item.id}">
    <div class="dashboard__card-title">${escHtml(item.title)}</div>
    <div class="dashboard__card-meta">
      <span>${item.source_type}${dur ? ' · ' + dur : ''}</span>
      <span>${ago}</span>
    </div>
    <div class="dashboard__card-progress">
      <div class="dashboard__card-progress-fill" style="width:${pct}%"></div>
    </div>
  </div>`;
}

function recentCard(item) {
  const dur = item.total_duration_ms > 0 ? formatTime(item.total_duration_ms) : '';
  const badge = !item.audio_ready && !dur ? 'no audio' : '';
  const ago = item.created_at ? timeAgo(item.created_at) : '';

  return `<div class="dashboard__card" data-item-id="${item.id}">
    <div class="dashboard__card-title">${escHtml(item.title)}</div>
    <div class="dashboard__card-meta">
      <span>${item.source_type}${dur ? ' · ' + dur : ''}${badge ? ' · ' + badge : ''}</span>
      <span>${ago}</span>
    </div>
  </div>`;
}

function stat(value, label) {
  return `<div class="dashboard__stat">
    <span class="dashboard__stat-value">${value}</span>${label}
  </div>`;
}
