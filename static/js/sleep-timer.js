// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

import { state } from './state.js';
import { toastSuccess } from './toast.js';
import { formatTime } from './utils.js';

let onTimerExpire = null;
let countdownInterval = null;

const btnSleep = document.getElementById('btn-sleep-timer');
const dropdown = document.getElementById('sleep-timer-dropdown');
const display = document.getElementById('sleep-timer-display');

const PRESETS = [
  { label: '15 min', minutes: 15 },
  { label: '30 min', minutes: 30 },
  { label: '45 min', minutes: 45 },
  { label: '1 hour', minutes: 60 },
  { label: 'End of item', minutes: -1 },
];

export function initSleepTimer({ onExpire }) {
  onTimerExpire = onExpire;

  btnSleep.addEventListener('click', e => {
    e.stopPropagation();
    if (state.sleepTimerEnd) {
      cancelTimer();
      toastSuccess('Sleep timer cancelled');
      return;
    }
    dropdown.classList.toggle('is-hidden');
  });

  PRESETS.forEach(p => {
    const el = document.createElement('div');
    el.className = 'sleep-timer__option';
    el.textContent = p.label;
    el.addEventListener('click', () => {
      dropdown.classList.add('is-hidden');
      startTimer(p.minutes);
    });
    dropdown.appendChild(el);
  });

  document.addEventListener('click', e => {
    if (!btnSleep.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add('is-hidden');
    }
  });
}

function startTimer(minutes) {
  cancelTimer();

  if (minutes === -1) {
    state.sleepTimerEnd = 'end-of-item';
    display.textContent = 'End of item';
    btnSleep.classList.add('is-active');
    toastSuccess('Sleep timer: end of item');
    return;
  }

  state.sleepTimerEnd = Date.now() + minutes * 60 * 1000;
  btnSleep.classList.add('is-active');
  toastSuccess(`Sleep timer: ${minutes} min`);
  updateDisplay();
  countdownInterval = setInterval(() => {
    if (Date.now() >= state.sleepTimerEnd) {
      cancelTimer();
      if (onTimerExpire) onTimerExpire();
      return;
    }
    updateDisplay();
  }, 1000);
}

function cancelTimer() {
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
  state.sleepTimerEnd = null;
  display.textContent = '';
  btnSleep.classList.remove('is-active');
}

function updateDisplay() {
  if (!state.sleepTimerEnd || state.sleepTimerEnd === 'end-of-item') return;
  const remaining = Math.max(0, state.sleepTimerEnd - Date.now());
  display.textContent = formatTime(remaining);
}

export function checkEndOfItem() {
  if (state.sleepTimerEnd === 'end-of-item') {
    cancelTimer();
    return true;
  }
  return false;
}
