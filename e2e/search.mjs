import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5194;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';
execSync(`mkdir -p ${DIR}`);

const server = spawn('uv', ['run', 'python', '-c', [
  "import sys, os, tempfile; sys.path.insert(0, '.')",
  "import models",
  "d = tempfile.mkdtemp()",
  "models.LIBRARY_DIR = d; models.DB_PATH = os.path.join(d, 't.db')",
  "models.AUDIO_DIR = os.path.join(d, 'audio'); models.IMAGES_DIR = os.path.join(d, 'images')",
  "models.THEMES_DIR = os.path.join(d, 'themes')",
  "from app import app, init_db",
  "init_db()",
  "sents = ['The alpha signal is strong.', 'We measured alpha twice today.', 'Finally alpha won the race.']",
  "models.add_item('Search Test', 'text', ' '.join(sents), sents)",
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

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(700);
  await page.locator('.item').first().click();
  await sleep(500);

  // Open search via button
  await page.locator('#btn-search').click();
  await sleep(200);
  check('search bar opens', await page.locator('#reader-search:not(.is-hidden)').count() > 0);

  // Query with 3 occurrences
  await page.fill('#reader-search-input', 'alpha');
  await sleep(300);
  const hitCount = await page.locator('mark.search-hit').count();
  check('all matches highlighted (3)', hitCount === 3);
  check('count shows 1/3', (await page.locator('#reader-search-count').textContent()) === '1/3');
  check('first hit is current', await page.locator('mark.search-hit.is-current').first().getAttribute('class').then(c => c.includes('is-current')));
  await page.screenshot({ path: `${DIR}/search-01-matches.png` });

  // Next
  await page.locator('#reader-search-next').click();
  await sleep(150);
  check('next -> 2/3', (await page.locator('#reader-search-count').textContent()) === '2/3');

  // Prev wraps to 1/3
  await page.locator('#reader-search-prev').click();
  await sleep(150);
  check('prev -> 1/3', (await page.locator('#reader-search-count').textContent()) === '1/3');
  await page.locator('#reader-search-prev').click();
  await sleep(150);
  check('prev wraps -> 3/3', (await page.locator('#reader-search-count').textContent()) === '3/3');

  // No-results query
  await page.fill('#reader-search-input', 'zzzznotfound');
  await sleep(300);
  check('no results message', (await page.locator('#reader-search-count').textContent()) === 'No results');
  check('no marks for missing query', await page.locator('mark.search-hit').count() === 0);

  // Close removes marks + hides bar
  await page.fill('#reader-search-input', 'alpha');
  await sleep(300);
  await page.locator('#reader-search-close').click();
  await sleep(150);
  check('close hides bar', await page.locator('#reader-search.is-hidden').count() > 0);
  check('close removes all marks', await page.locator('mark.search-hit').count() === 0);

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
