export async function api(path, opts = {}) {
  try {
    const res = await fetch(path, {
      method: opts.method || (opts.body ? 'POST' : 'GET'),
      headers: opts.body ? { 'Content-Type': 'application/json' } : {},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    return res.json();
  } catch (e) {
    console.error('API error:', path, e);
    return { error: e.message };
  }
}

export function connectSSE(handlers) {
  const source = new EventSource('/api/events');
  for (const [event, handler] of Object.entries(handlers)) {
    source.addEventListener(event, e => handler(JSON.parse(e.data)));
  }
  return source;
}
