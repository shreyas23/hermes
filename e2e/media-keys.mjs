import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5195;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';
execSync(`mkdir -p ${DIR}`);

// Isolated temp library seeded with one audio-ready item (silent WAV) so the
// player can actually start without TTS or touching the real library.
const server = spawn('uv', ['run', 'python', '-c', [
  "import sys, os, tempfile, wave; sys.path.insert(0, '.')",
  "import models",
  "d = tempfile.mkdtemp()",
  "models.LIBRARY_DIR = d; models.DB_PATH = os.path.join(d, 't.db')",
  "models.AUDIO_DIR = os.path.join(d, 'audio'); models.IMAGES_DIR = os.path.join(d, 'images')",
  "models.THEMES_DIR = os.path.join(d, 'themes')",
  "from app import app, init_db",
  "init_db()",
  "iid = models.add_item('Seeded Audio Item', 'text', 'First sentence here. Second sentence here.', ['First sentence here.', 'Second sentence here.'])",
  "os.makedirs(models.item_audio_dir(iid), exist_ok=True)",
  "w = wave.open(models.item_master_wav(iid), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b'\\x00\\x00' * 44100); w.close()",
  "models.update_item_audio(iid, [{'index': 0, 'start_ms': 0, 'duration_ms': 1000}, {'index': 1, 'start_ms': 1000, 'duration_ms': 1000}], 2000)",
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
  await sleep(800);

  check('mediaSession supported', await page.evaluate(() => 'mediaSession' in navigator));
  const actions = await page.evaluate(() => window.__mediaSessionActions || []);
  for (const a of ['play', 'pause', 'previoustrack', 'nexttrack', 'seekbackward', 'seekforward'])
    check(`action handler registered: ${a}`, actions.includes(a));

  await page.locator('.item').first().click();
  await sleep(500);

  await page.locator('#btn-play').click();
  await sleep(800);
  const playing = await page.evaluate(() => ({
    title: navigator.mediaSession.metadata?.title,
    state: navigator.mediaSession.playbackState,
  }));
  check('metadata title set on play', playing.title === 'Seeded Audio Item');
  check('playbackState = playing', playing.state === 'playing');

  await page.locator('#btn-pause').click();
  await sleep(400);
  const paused = await page.evaluate(() => navigator.mediaSession.playbackState);
  check('playbackState = paused after pause', paused === 'paused');

  const realErrors = errors.filter(e => !e.includes('AbortError'));
  console.log('\nConsole/page errors:', realErrors.length ? realErrors : 'none');
  const failed = results.filter(([, c]) => !c).map(([n]) => n);
  console.log(failed.length ? `\nFAILED: ${failed.join(', ')}` : '\nALL CHECKS PASSED');
  process.exitCode = (failed.length || realErrors.length) ? 1 : 0;
} catch (e) {
  console.error('TEST ERROR:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
  server.kill();
}
