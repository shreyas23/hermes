import { api } from './api.js';
import { toastSuccess, toastError } from './toast.js';
import { escHtml } from './utils.js';

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

const watchList = document.getElementById('watch-folders-list');
const watchInput = document.getElementById('watch-folder-path');
const watchAddBtn = document.getElementById('watch-folder-add-btn');

export function initSettings() {
  document.getElementById('btn-settings').addEventListener('click', open);
  document.getElementById('settings-backdrop').addEventListener('click', close);
  document.getElementById('settings-close').addEventListener('click', close);
  document.getElementById('settings-save').addEventListener('click', save);

  watchAddBtn.addEventListener('click', addWatchFolder);
  watchInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') addWatchFolder();
  });

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
  loadWatchFolders();

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

async function loadWatchFolders() {
  const data = await api('/api/watch-folders', { showError: false });
  if (!data.folders) return;
  watchList.innerHTML = '';
  if (data.folders.length === 0) {
    watchList.innerHTML = '<div class="watch-folders__empty">No watch folders</div>';
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
    watchList.appendChild(el);
  });
}

async function addWatchFolder() {
  const path = watchInput.value.trim();
  if (!path) return;
  const data = await api('/api/watch-folders', { body: { path }, showError: false });
  if (data.error) {
    toastError(data.error);
    return;
  }
  watchInput.value = '';
  loadWatchFolders();
}
