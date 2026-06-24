// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

export function formatTime(ms) {
  if (!ms || !isFinite(ms)) return '0:00';
  const totalSec = Math.floor(ms / 1000);
  const hrs = Math.floor(totalSec / 3600);
  const min = Math.floor((totalSec % 3600) / 60);
  const sec = totalSec % 60;
  if (hrs > 0) return `${hrs}:${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  return `${min}:${sec.toString().padStart(2, '0')}`;
}

export function escHtml(str) {
  const el = document.createElement('span');
  el.textContent = str;
  return el.innerHTML;
}

export function isYouTubeUrl(url) {
  return /^https?:\/\/(www\.|m\.)?(youtube\.com\/(watch|shorts|embed|v\/)|youtu\.be\/)/i.test(url);
}

export function timeAgo(epochSec) {
  const diff = Date.now() / 1000 - epochSec;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(epochSec * 1000).toLocaleDateString();
}
