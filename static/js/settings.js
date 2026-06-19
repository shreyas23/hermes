import { api } from './api.js';
import { toastSuccess } from './toast.js';

const modal = document.getElementById('settings-modal');
const engineSelect = document.getElementById('setting-engine');
const edgeVoiceSelect = document.getElementById('setting-edge-voice');
const sayVoiceSelect = document.getElementById('setting-say-voice');
const edgeGroup = document.getElementById('edge-voice-group');
const sayGroup = document.getElementById('say-voice-group');

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
  const [settings, edgeVoices, sayVoices] = await Promise.all([
    api('/api/settings'),
    api('/api/voices?engine=edge'),
    api('/api/voices?engine=say'),
  ]);

  engineSelect.value = settings.tts_engine || 'edge';

  if (edgeVoices.voices) populateSelect(edgeVoiceSelect, edgeVoices.voices, v => `${v.name} (${v.gender})`);
  edgeVoiceSelect.value = settings.edge_voice || 'en-US-AriaNeural';

  if (sayVoices.voices) populateSelect(sayVoiceSelect, sayVoices.voices, v => v.name);
  sayVoiceSelect.value = settings.say_voice || 'Samantha';

  const isEdge = engineSelect.value === 'edge';
  edgeGroup.classList.toggle('is-hidden', !isEdge);
  sayGroup.classList.toggle('is-hidden', isEdge);

  modal.classList.add('is-visible');
}

function close() {
  modal.classList.remove('is-visible');
}

async function save() {
  await api('/api/settings', {
    body: {
      tts_engine: engineSelect.value,
      edge_voice: edgeVoiceSelect.value,
      say_voice: sayVoiceSelect.value,
    }
  });
  toastSuccess('Settings saved');
  close();
}
