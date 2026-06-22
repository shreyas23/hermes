import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

export { sleep };

export async function startServer(port, setupCode = '') {
  const base = `http://127.0.0.1:${port}`;
  const code = [
    "import sys, os, tempfile; sys.path.insert(0, '.')",
    "import models",
    "d = tempfile.mkdtemp()",
    "models.LIBRARY_DIR = d; models.DB_PATH = os.path.join(d, 't.db')",
    "models.AUDIO_DIR = os.path.join(d, 'audio'); models.IMAGES_DIR = os.path.join(d, 'images')",
    "from app import app, init_db",
    "init_db()",
    setupCode,
    `app.run(port=${port}, threaded=True, use_reloader=False)`,
  ].filter(Boolean).join('\n');

  const server = spawn('/opt/homebrew/bin/uv', ['run', 'python', '-c', code], { stdio: 'pipe' });
  server.stderr.on('data', d => {
    const s = d.toString();
    if (s.includes('Traceback') || (s.includes('Error') && !s.includes('WARNING')))
      console.error('SERVER:', s.trim());
  });

  for (let i = 0; i < 30; i++) {
    try { await fetch(base); break; } catch { await sleep(500); }
  }
  console.log('Server ready');
  return { server, base };
}

export async function startBrowser(base, opts = {}) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  return { browser, page, errors };
}

export function makeChecker() {
  const results = [];
  const check = (name, cond) => { results.push([name, cond]); console.log(`${cond ? 'PASS' : 'FAIL'} — ${name}`); };
  const summary = (errors = []) => {
    console.log('\nConsole/page errors:', errors.length ? errors : 'none');
    const failed = results.filter(([, c]) => !c).map(([n]) => n);
    console.log(failed.length ? `\nFAILED: ${failed.join(', ')}` : '\nALL CHECKS PASSED');
    process.exitCode = (failed.length || errors.length) ? 1 : 0;
  };
  return { check, summary };
}
