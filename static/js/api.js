// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

import { toastError } from './toast.js';

export async function api(path, opts = {}) {
  try {
    const res = await fetch(path, {
      method: opts.method || (opts.body ? 'POST' : 'GET'),
      headers: opts.body ? { 'Content-Type': 'application/json' } : {},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json();
    if (data.error && opts.showError !== false) {
      toastError(data.error);
    }
    return data;
  } catch (e) {
    console.error('API error:', path, e);
    if (opts.showError !== false) toastError('Connection error');
    return { error: e.message };
  }
}

export function connectSSE(handlers) {
  let source;
  let retryDelay = 1000;

  function connect() {
    source = new EventSource('/api/events');
    for (const [event, handler] of Object.entries(handlers)) {
      source.addEventListener(event, e => handler(JSON.parse(e.data)));
    }
    source.onopen = () => { retryDelay = 1000; };
    source.onerror = () => {
      source.close();
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 30000);
    };
  }

  connect();
  return source;
}
