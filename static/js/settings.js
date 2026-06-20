import { api } from './api.js';
import { toastSuccess } from './toast.js';

const modal = document.getElementById('settings-modal');
const engineSelect = document.getElementById('setting-engine');
const edgeVoiceSelect = document.getElementById('setting-edge-voice');
const sayVoiceSelect = document.getElementById('setting-say-voice');
const designSelect = document.getElementById('setting-design');
const edgeGroup = document.getElementById('edge-voice-group');
const sayGroup = document.getElementById('say-voice-group');
const themeBtn = document.getElementById('btn-theme');
const themeIcon = document.getElementById('theme-icon');

let cachedEdgeVoices = null;
let cachedSayVoices = null;

export function initSettings() {
  document.getElementById('btn-settings').addEventListener('click', open);
  document.getElementById('settings-backdrop').addEventListener('click', close);
  document.getElementById('settings-close').addEventListener('click', close);
  document.getElementById('settings-save').addEventListener('click', save);

  engineSelect.addEventListener('change', () => {
    const isEdge = engineSelect.value === 'edge';
    edgeGroup.classList.toggle('is-hidden', !isEdge);
    sayGroup.classList.toggle('is-hidden', isEdge);
  });

  designSelect.addEventListener('change', () => {
    document.documentElement.setAttribute('data-design', designSelect.value);
    localStorage.setItem('hermes-design', designSelect.value);
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

  const [settings, edgeVoices, sayVoices] = await Promise.all([
    api('/api/settings'),
    cachedEdgeVoices ?? api('/api/voices?engine=edge').then(r => (cachedEdgeVoices = r.voices)),
    cachedSayVoices ?? api('/api/voices?engine=say').then(r => (cachedSayVoices = r.voices)),
  ]);

  engineSelect.value = settings.tts_engine || 'edge';
  designSelect.value = settings.design || localStorage.getItem('hermes-design') || 'glass';

  if (edgeVoices) populateSelect(edgeVoiceSelect, edgeVoices, v => `${v.name} (${v.gender})`);
  edgeVoiceSelect.value = settings.edge_voice || 'en-US-AriaNeural';

  if (sayVoices) populateSelect(sayVoiceSelect, sayVoices, v => v.name);
  sayVoiceSelect.value = settings.say_voice || 'Samantha';

  const isEdge = engineSelect.value === 'edge';
  edgeGroup.classList.toggle('is-hidden', !isEdge);
  sayGroup.classList.toggle('is-hidden', isEdge);
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
    }
  });
  toastSuccess('Settings saved');
  close();
}
