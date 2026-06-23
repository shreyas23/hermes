import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { writeFileSync, mkdirSync, unlinkSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PORT = 5199;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';

execSync(`mkdir -p ${DIR}`);

const server = spawn('uv', ['run', 'python', '-c', [
  "import sys; sys.path.insert(0, '.')",
  "import models; models.DB_PATH = '/tmp/hermes-test-dragdrop.db'; models.AUDIO_DIR = '/tmp/hermes-test-audio'; models.IMAGES_DIR = '/tmp/hermes-test-images'",
  "from app import app, init_db",
  "init_db()",
  `app.run(port=${PORT}, threaded=True, use_reloader=False)`,
].join('\n')], { stdio: 'pipe' });

server.stderr.on('data', d => {
  const s = d.toString();
  if (s.includes('Traceback') || (s.includes('Error') && !s.includes('WARNING')))
    console.error(s.trim());
});

for (let i = 0; i < 30; i++) {
  try { await fetch(BASE); break; } catch { await sleep(500); }
}
console.log('Server ready');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });

page.on('console', msg => {
  if (msg.type() === 'error') console.error('CONSOLE ERROR:', msg.text());
});

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1000);

  // === Test 1: File upload endpoint (simulates drag-and-drop backend) ===
  const tmpFile = join(tmpdir(), 'hermes-test-import.txt');
  writeFileSync(tmpFile, 'This is a test document for drag and drop import. It has enough text to be imported successfully into the Hermes library.');

  const uploadRes = await page.evaluate(async () => {
    const text = 'This is a test document for drag and drop import. It has enough text to be imported successfully into the Hermes library.';
    const blob = new Blob([text], { type: 'text/plain' });
    const form = new FormData();
    form.append('file', blob, 'test-drag-drop.txt');
    const res = await fetch('/api/import/upload', { method: 'POST', body: form });
    return res.json();
  });

  if (uploadRes.error) {
    console.error('Upload failed:', uploadRes.error);
  } else {
    console.log(`Upload OK — item_id=${uploadRes.item_id}, title="${uploadRes.title}"`);
    await sleep(500);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await sleep(1000);
    await page.screenshot({ path: `${DIR}/20-after-upload.png` });
    console.log('20-after-upload.png — library after file upload import');
  }

  // === Test 2: Drop overlay appears (simulate via JS class toggle) ===
  await page.evaluate(() => document.getElementById('drop-overlay').classList.add('is-visible'));
  await sleep(300);
  await page.screenshot({ path: `${DIR}/21-drop-overlay.png` });
  console.log('21-drop-overlay.png — drop overlay visible');
  await page.evaluate(() => document.getElementById('drop-overlay').classList.remove('is-visible'));

  // === Test 3: Settings modal with watch folders ===
  await page.click('#btn-settings');
  await sleep(500);
  await page.screenshot({ path: `${DIR}/22-settings-watch-folders.png` });
  console.log('22-settings-watch-folders.png — settings with watch folders section');

  // === Test 4: Add a watch folder ===
  const watchDir = join(tmpdir(), 'hermes-test-watch');
  try { mkdirSync(watchDir, { recursive: true }); } catch {}

  await page.fill('#watch-folder-path', watchDir);
  await page.click('#watch-folder-add-btn');
  await sleep(500);
  await page.screenshot({ path: `${DIR}/23-watch-folder-added.png` });
  console.log('23-watch-folder-added.png — watch folder added');

  // === Test 5: Remove the watch folder ===
  const removeBtn = page.locator('.watch-folder__remove').first();
  if (await removeBtn.isVisible()) {
    await removeBtn.click();
    await sleep(500);
    await page.screenshot({ path: `${DIR}/24-watch-folder-removed.png` });
    console.log('24-watch-folder-removed.png — watch folder removed');
  }

  // Close settings
  await page.click('#settings-close');

  // Cleanup
  try { unlinkSync(tmpFile); } catch {}
  try { rmdirSync(watchDir); } catch {}

  console.log(`\nDone — screenshots in ${DIR}/`);
} finally {
  await browser.close();
  server.kill();
  try { unlinkSync('/tmp/hermes-test-dragdrop.db'); } catch {}
}
