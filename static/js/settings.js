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

async function open() {
  const settings = await api('/api/settings');

  engineSelect.value = settings.tts_engine || 'edge';

  const edgeVoices = await api('/api/voices?engine=edge');
  edgeVoiceSelect.innerHTML = '';
  if (edgeVoices.voices) {
    edgeVoices.voices.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.gender})`;
      edgeVoiceSelect.appendChild(opt);
    });
  }
  edgeVoiceSelect.value = settings.edge_voice || 'en-US-AriaNeural';

  const sayVoices = await api('/api/voices?engine=say');
  sayVoiceSelect.innerHTML = '';
  if (sayVoices.voices) {
    sayVoices.voices.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.id;
      opt.textContent = v.name;
      sayVoiceSelect.appendChild(opt);
    });
  }
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
