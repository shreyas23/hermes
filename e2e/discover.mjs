import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5199;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';

execSync(`mkdir -p ${DIR}`);

// Own server on an isolated temp library so the real ~/hermes-library is untouched.
const server = spawn('/opt/homebrew/bin/uv', ['run', 'python', '-c', [
  "import sys, os, tempfile; sys.path.insert(0, '.')",
  "import models",
  "d = tempfile.mkdtemp()",
  "models.LIBRARY_DIR = d",
  "models.DB_PATH = os.path.join(d, 't.db')",
  "models.AUDIO_DIR = os.path.join(d, 'audio')",
  "models.IMAGES_DIR = os.path.join(d, 'images')",
  "from app import app, init_db",
  "init_db()",
  `app.run(port=${PORT}, threaded=True, use_reloader=False)`,
].join('\n')], { stdio: 'pipe' });

server.stderr.on('data', d => {
  const s = d.toString();
  if (s.includes('Traceback') || (s.includes('Error') && !s.includes('WARNING')))
    console.error('SERVER:', s.trim());
});

for (let i = 0; i < 30; i++) {
  try { await fetch(BASE); break; } catch { await sleep(500); }
}
console.log('Server ready');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));

const results = [];
const check = (name, cond) => { results.push([name, cond]); console.log(`${cond ? 'PASS' : 'FAIL'} — ${name}`); };

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(800);

  // No mini-player anywhere (removed)
  check('mini-player removed from DOM', await page.locator('#mini-player').count() === 0);

  // --- Discover: Search tab ---
  await page.click('#btn-discover');
  await sleep(400);
  await page.screenshot({ path: `${DIR}/discover-01-search.png` });
  check('Discover modal opens', await page.locator('#discover-modal.is-visible').count() > 0);

  await page.fill('#discover-search-input', 'Barack Obama');
  await page.click('#discover-search-btn');
  await page.waitForSelector('.discover__result', { timeout: 15000 });
  await sleep(300);
  const nResults = await page.locator('.discover__result').count();
  await page.screenshot({ path: `${DIR}/discover-02-results.png` });
  check('Wikipedia search returns results', nResults > 0);

  // Import first result -> pending item (opt-in: no audio generated)
  await page.locator('.discover__result .discover__add').first().click();
  await page.waitForSelector('.discover__add.is-done', { timeout: 25000 });
  check('Add marks result as Added', await page.locator('.discover__add.is-done').count() > 0);

  // --- Feeds tab ---
  await page.click('.modal__tab[data-tab="feeds"]');
  await sleep(500);
  await page.screenshot({ path: `${DIR}/discover-03-feeds.png` });
  check('Feeds tab renders', await page.locator('#discover-pane-feeds.is-active').count() > 0);

  // Footer has both Done and Cancel
  check('Done button present', await page.locator('#discover-done').count() > 0);
  check('Cancel button present', await page.locator('#discover-close').count() > 0);

  // Close via Done
  await page.click('#discover-done');
  await sleep(300);
  check('Done closes modal', await page.locator('#discover-modal.is-visible').count() === 0);

  // --- Opt-in audio bar on the pending item ---
  await page.locator('.item').first().click();
  await sleep(700);
  await page.screenshot({ path: `${DIR}/discover-04-pending.png` });
  check('Generate-audio bar shown for pending item',
    await page.locator('#audio-gen:not(.is-hidden) #audio-gen-action').count() > 0);
  check('Transport controls hidden for pending item',
    await page.locator('.controls.is-hidden').count() > 0);
  check('Pending badge in sidebar', await page.locator('.badge--pending').count() > 0);

  // --- Custom delete confirmation modal ---
  await page.hover('.item');
  await page.locator('.item .item__delete').first().click();
  await sleep(300);
  await page.screenshot({ path: `${DIR}/discover-05-confirm.png` });
  check('Delete confirm modal opens', await page.locator('#confirm-modal.is-visible').count() > 0);
  // Cancel keeps the item
  await page.click('#confirm-cancel');
  await sleep(300);
  check('Cancel dismisses confirm', await page.locator('#confirm-modal.is-visible').count() === 0);
  check('Item still present after cancel', await page.locator('.item').count() > 0);

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
