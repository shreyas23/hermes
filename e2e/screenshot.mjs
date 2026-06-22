import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5197;
const BASE = `http://127.0.0.1:${PORT}`;
const DIR = 'e2e/screenshots';

execSync(`mkdir -p ${DIR}`);

const server = spawn('/opt/homebrew/bin/uv', ['run', 'python', '-c', [
  "import sys; sys.path.insert(0, '.')",
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

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1000);
  await page.screenshot({ path: `${DIR}/01-empty.png` });
  console.log('01-empty.png — empty state');

  // Audio is opt-in: pending items have no player. Pick items that already have
  // audio (audio-ready items carry no status badge in the sidebar).
  const readyItems = page.locator('.item:not(:has(.badge))');
  if (await readyItems.count() > 0) {
    await readyItems.first().click();
    await sleep(500);
    await page.screenshot({ path: `${DIR}/02-item-open.png` });
    console.log('02-item-open.png — item open');

    const playBtn = page.locator('#btn-play');
    if (await playBtn.isVisible()) {
      await playBtn.click();
      await sleep(1000);
      await page.screenshot({ path: `${DIR}/03-playing.png` });
      console.log('03-playing.png — playing');

      if (await readyItems.count() > 1) {
        await readyItems.nth(1).click();
        await sleep(500);
        await page.screenshot({ path: `${DIR}/04-remote-playing.png` });
        console.log('04-remote-playing.png — viewing different item while playing');
      }
    }
  } else {
    console.log('No audio-ready items — skipping player screenshots (opt-in audio)');
  }

  console.log(`\nDone — screenshots in ${DIR}/`);
} finally {
  await browser.close();
  server.kill();
}
