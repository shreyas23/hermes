import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5193;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';
execSync(`mkdir -p ${DIR}`);

const server = spawn('/opt/homebrew/bin/uv', ['run', 'python', '-c', [
  "import sys, os, tempfile; sys.path.insert(0, '.')",
  "import models",
  "d = tempfile.mkdtemp()",
  "models.LIBRARY_DIR = d; models.DB_PATH = os.path.join(d, 't.db')",
  "models.AUDIO_DIR = os.path.join(d, 'audio'); models.IMAGES_DIR = os.path.join(d, 'images')",
  "from app import app, init_db",
  "init_db()",
  "sents = ['First passage about gravity.', 'Second passage about momentum.', 'Third passage about energy.']",
  "models.add_item('Notes Test', 'text', ' '.join(sents), sents)",
  `app.run(port=${PORT}, threaded=True, use_reloader=False)`,
].join('\n')], { stdio: 'pipe' });
server.stderr.on('data', d => { const s = d.toString(); if (s.includes('Traceback') || (s.includes('Error') && !s.includes('WARNING'))) console.error('SERVER:', s.trim()); });

for (let i = 0; i < 30; i++) { try { await fetch(BASE); break; } catch { await sleep(500); } }
console.log('Server ready');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));

const results = [];
const check = (name, cond) => { results.push([name, cond]); console.log(`${cond ? 'PASS' : 'FAIL'} — ${name}`); };

async function openItem() {
  await page.locator('.item').first().click();
  await sleep(400);
}

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(700);
  await openItem();

  // Select the 2nd sentence, then bookmark it
  await page.locator('[data-si="1"]').click();
  await sleep(100);
  await page.locator('#btn-bookmarks').click();
  await sleep(200);
  check('bookmarks panel opens', await page.locator('#reader-bookmarks:not(.is-hidden)').count() > 0);

  await page.locator('#bookmark-add').click();
  await sleep(300);
  check('bookmark added (1 row)', await page.locator('.bookmark').count() === 1);
  check('bookmark quote = selected sentence',
    (await page.locator('.bookmark__quote').first().textContent())?.trim() === 'Second passage about momentum.');
  await page.screenshot({ path: `${DIR}/bookmarks-01-added.png` });

  // Annotation: type a note and persist it
  const note = page.locator('.bookmark__note').first();
  await note.fill('Revisit this argument');
  await note.press('Enter');
  await sleep(400);

  // Reload and confirm the annotation persisted (server-side)
  await page.reload({ waitUntil: 'domcontentloaded' });
  await sleep(700);
  await openItem();
  await page.locator('#btn-bookmarks').click();
  await sleep(300);
  check('bookmark persists after reload', await page.locator('.bookmark').count() === 1);
  check('annotation note persists',
    (await page.locator('.bookmark__note').first().inputValue()) === 'Revisit this argument');

  // Jump: clicking the quote flashes the target sentence (no audio -> scroll/flash)
  await page.locator('.bookmark__quote').first().click();
  await sleep(150);
  check('jump flashes target sentence', await page.locator('[data-si="1"].is-flash').count() > 0);

  // Delete
  await page.locator('.bookmark__delete').first().click();
  await sleep(300);
  check('bookmark deleted (empty state)', await page.locator('.bookmark').count() === 0);

  console.log('\nConsole/page errors:', errors.length ? errors : 'none');
  const failed = results.filter(([, c]) => !c).map(([n]) => n);
  console.log(failed.length ? `\nFAILED: ${failed.join(', ')}` : '\nALL CHECKS PASSED');
  process.exitCode = (failed.length || errors.length) ? 1 : 0;
} catch (e) {
  console.error('TEST ERROR:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
  server.kill();
}
