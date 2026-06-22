const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2];

const state = {
  currentItemId: null,
  currentItem: null,
  playingItemId: null,
  playingItem: null,
  playing: false,
  audio: new Audio(),
  timeline: [],
  totalDurationMs: 0,
  tickInterval: null,
  progressSaveInterval: null,
  currentView: 'recent',
  speedIndex: 2,
  scrubbing: false,
  queue: [],
  sleepTimerEnd: null,
};

export { state, SPEED_OPTIONS };
