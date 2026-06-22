import { api } from './api.js';
import { toastSuccess } from './toast.js';

const modal = document.getElementById('settings-modal');
const engineSelect = document.getElementById('setting-engine');
const edgeVoiceSelect = document.getElementById('setting-edge-voice');
const sayVoiceSelect = document.getElementById('setting-say-voice');
const kokoroVoiceSelect = document.getElementById('setting-kokoro-voice');
const kokoroMlxVoiceSelect = document.getElementById('setting-kokoro-mlx-voice');
const piperVoiceSelect = document.getElementById('setting-piper-voice');
const designSelect = document.getElementById('setting-design');
const edgeGroup = document.getElementById('edge-voice-group');
const sayGroup = document.getElementById('say-voice-group');
const kokoroGroup = document.getElementById('kokoro-voice-group');
const kokoroMlxGroup = document.getElementById('kokoro-mlx-voice-group');
const piperGroup = document.getElementById('piper-voice-group');
const themeBtn = document.getElementById('btn-theme');
const themeIcon = document.getElementById('theme-icon');

let cachedEdgeVoices = null;
let cachedSayVoices = null;
let cachedKokoroVoices = null;
let cachedPiperVoices = null;

function updateVoiceGroups(engine) {
  edgeGroup.classList.toggle('is-hidden', engine !== 'edge');
  sayGroup.classList.toggle('is-hidden', engine !== 'say');
  kokoroGroup.classList.toggle('is-hidden', engine !== 'kokoro');
  kokoroMlxGroup.classList.toggle('is-hidden', engine !== 'kokoro-mlx');
  piperGroup.classList.toggle('is-hidden', engine !== 'piper');
}

export function initSettings() {
  document.getElementById('btn-settings').addEventListener('click', open);
  document.getElementById('settings-backdrop').addEventListener('click', close);
  document.getElementById('settings-close').addEventListener('click', close);
  document.getElementById('settings-save').addEventListener('click', save);

  engineSelect.addEventListener('change', () => updateVoiceGroups(engineSelect.value));

  designSelect.addEventListener('change', () => {
    document.documentElement.setAttribute('data-design', designSelect.value);
    localStorage.setItem('hermes-design', designSelect.value);
    api('/api/settings', { body: { design: designSelect.value } });
  });

  updateThemeIcon();
  themeBtn.addEventListener('click', toggleTheme);
}

function populateSelect(select, voices, labelFn) {
  select.innerHTML = '';
  voices.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v.id;
    opt.textContent = labelFn(v);
    select.appendChild(opt);
  });
}

async function open() {
  modal.classList.add('is-visible');
  loadStats();
  loadCache();

  const [settings, edgeVoices, sayVoices, kokoroVoices, piperVoices] = await Promise.all([
    api('/api/settings'),
    cachedEdgeVoices ?? api('/api/voices?engine=edge').then(r => (cachedEdgeVoices = r.voices)),
    cachedSayVoices ?? api('/api/voices?engine=say').then(r => (cachedSayVoices = r.voices)),
    cachedKokoroVoices ?? api('/api/voices?engine=kokoro').then(r => (cachedKokoroVoices = r.voices)),
    cachedPiperVoices ?? api('/api/voices?engine=piper').then(r => (cachedPiperVoices = r.voices)),
  ]);

  engineSelect.value = settings.tts_engine || 'edge';
  designSelect.value = settings.design || localStorage.getItem('hermes-design') || window.__DEFAULT_DESIGN;

  if (edgeVoices) populateSelect(edgeVoiceSelect, edgeVoices, v => `${v.name} (${v.gender})`);
  edgeVoiceSelect.value = settings.edge_voice || 'en-US-AriaNeural';

  if (sayVoices) populateSelect(sayVoiceSelect, sayVoices, v => v.name);
  sayVoiceSelect.value = settings.say_voice || 'Samantha';

  const kokoroLabelFn = v => `${v.name} (${v.gender}, ${v.locale})`;
  if (kokoroVoices) {
    populateSelect(kokoroVoiceSelect, kokoroVoices, kokoroLabelFn);
    populateSelect(kokoroMlxVoiceSelect, kokoroVoices, kokoroLabelFn);
  }
  kokoroVoiceSelect.value = settings.kokoro_voice || 'af_heart';
  kokoroMlxVoiceSelect.value = settings['kokoro-mlx_voice'] || 'af_heart';

  if (piperVoices) populateSelect(piperVoiceSelect, piperVoices, v => `${v.name} (${v.locale})`);
  piperVoiceSelect.value = settings.piper_voice || 'en_US-lessac-medium';

  updateVoiceGroups(engineSelect.value);
}

function close() {
  modal.classList.remove('is-visible');
}

function isDark() {
  return document.documentElement.getAttribute('data-theme') === 'dark';
}

function updateThemeIcon() {
  themeIcon.textContent = isDark() ? '☀' : '☾';
}

function toggleTheme() {
  const theme = isDark() ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('hermes-theme', theme);
  updateThemeIcon();
  api('/api/settings', { body: { theme } });
}

async function save() {
  await api('/api/settings', {
    body: {
      design: designSelect.value,
      tts_engine: engineSelect.value,
      edge_voice: edgeVoiceSelect.value,
      say_voice: sayVoiceSelect.value,
      kokoro_voice: kokoroVoiceSelect.value,
      'kokoro-mlx_voice': kokoroMlxVoiceSelect.value,
      piper_voice: piperVoiceSelect.value,
    }
  });
  toastSuccess('Settings saved');
  close();
}


function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

async function loadStats() {
  const el = document.getElementById('settings-stats');
  const data = await api('/api/stats', { showError: false });
  if (!data || data.error) { el.innerHTML = '<div class="settings-stats__loading">Unavailable</div>'; return; }

  el.innerHTML = `
    <div class="settings-stat"><span>Library items</span><span class="settings-stat__value">${data.items}</span></div>
    <div class="settings-stat"><span>With audio</span><span class="settings-stat__value">${data.audio_items}</span></div>
    <div class="settings-stat"><span>Total audio</span><span class="settings-stat__value">${formatDuration(data.total_duration_ms)}</span></div>
    <div class="settings-stat"><span>Bookmarks</span><span class="settings-stat__value">${data.bookmarks}</span></div>
    <div class="settings-stat"><span>Feeds</span><span class="settings-stat__value">${data.feeds}</span></div>
    <div class="settings-stat"><span>Collections</span><span class="settings-stat__value">${data.collections}</span></div>
  `;
}

async function loadCache() {
  const el = document.getElementById('settings-cache');
  const data = await api('/api/stats', { showError: false });
  if (!data || data.error) { el.innerHTML = '<div class="settings-stats__loading">Unavailable</div>'; return; }

  el.innerHTML = `
    <div class="settings-cache__row">
      <div class="settings-cache__info">
        <span class="settings-cache__label">Audio cache</span>
        <span class="settings-cache__size">${formatBytes(data.audio_cache_bytes)}</span>
      </div>
    </div>
    <div class="settings-cache__row">
      <div class="settings-cache__info">
        <span class="settings-cache__label">TTS models</span>
        <span class="settings-cache__size">${formatBytes(data.models_cache_bytes)}</span>
      </div>
      <button class="settings-cache__btn" data-target="models">Clear</button>
    </div>
    <div class="settings-cache__row">
      <div class="settings-cache__info">
        <span class="settings-cache__label">HuggingFace cache</span>
        <span class="settings-cache__size">${formatBytes(data.hf_cache_bytes)}</span>
      </div>
      <button class="settings-cache__btn" data-target="hf">Clear</button>
    </div>
  `;

  el.querySelectorAll('.settings-cache__btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const target = btn.dataset.target;
      btn.textContent = '...';
      await api('/api/cache/clear', { body: { target } });
      toastSuccess(`${target === 'hf' ? 'HuggingFace' : 'Model'} cache cleared`);
      loadCache();
    });
  });
}
