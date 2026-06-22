import { chromium } from 'playwright';
import { execSync, spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = 5199;
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

// Collect console errors
page.on('console', msg => {
  if (msg.type() === 'error') console.error('CONSOLE ERROR:', msg.text());
});

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1000);

  const readyItems = page.locator('.item:not(:has(.badge))');
  const itemCount = await readyItems.count();
  if (itemCount === 0) {
    console.log('No audio-ready items — cannot test queue/timer');
    process.exit(0);
  }

  // Open first item to show controls
  await readyItems.first().click();
  await sleep(500);

  // Screenshot: controls with new buttons visible
  await page.screenshot({ path: `${DIR}/10-controls-buttons.png` });
  console.log('10-controls-buttons.png — controls with queue + sleep timer buttons');

  // Click queue button to open panel
  await page.click('#btn-queue');
  await sleep(300);
  await page.screenshot({ path: `${DIR}/11-queue-panel-empty.png` });
  console.log('11-queue-panel-empty.png — empty queue panel');

  // Close queue panel
  await page.click('#btn-queue');
  await sleep(200);

  // Right-click an audio-ready item to see context menu with queue actions
  if (itemCount > 1) {
    await readyItems.nth(1).click({ button: 'right' });
    await sleep(300);
    await page.screenshot({ path: `${DIR}/12-context-menu-queue.png` });
    console.log('12-context-menu-queue.png — context menu with Play Next / Add to Queue');

    // Click "Add to Queue"
    const addToQueue = page.locator('.context-menu__item', { hasText: 'Add to Queue' });
    if (await addToQueue.isVisible()) {
      await addToQueue.click();
      await sleep(500);

      // Open queue panel to see the item
      await page.click('#btn-queue');
      await sleep(300);
      await page.screenshot({ path: `${DIR}/13-queue-panel-with-item.png` });
      console.log('13-queue-panel-with-item.png — queue panel with one item');

      // Close queue panel
      await page.click('#btn-queue');
      await sleep(200);
    }
  }

  // Click sleep timer button to show dropdown
  await page.click('#btn-sleep-timer');
  await sleep(300);
  await page.screenshot({ path: `${DIR}/14-sleep-timer-dropdown.png` });
  console.log('14-sleep-timer-dropdown.png — sleep timer options');

  // Select 15 min
  const opt15 = page.locator('.sleep-timer__option', { hasText: '15 min' });
  if (await opt15.isVisible()) {
    await opt15.click();
    await sleep(500);
    await page.screenshot({ path: `${DIR}/15-sleep-timer-active.png` });
    console.log('15-sleep-timer-active.png — sleep timer countdown active');
  }

  // Cancel sleep timer by clicking button again
  await page.click('#btn-sleep-timer');
  await sleep(300);

  // Test adding multiple items to queue via Play Next
  if (itemCount > 2) {
    await readyItems.nth(2).click({ button: 'right' });
    await sleep(200);
    const playNext = page.locator('.context-menu__item', { hasText: 'Play Next' });
    if (await playNext.isVisible()) {
      await playNext.click();
      await sleep(300);
    }

    // Open queue to see both items
    await page.click('#btn-queue');
    await sleep(300);
    await page.screenshot({ path: `${DIR}/16-queue-multiple.png` });
    console.log('16-queue-multiple.png — queue with multiple items');
  }

  console.log(`\nDone — screenshots in ${DIR}/`);
} finally {
  await browser.close();
  server.kill();
}
