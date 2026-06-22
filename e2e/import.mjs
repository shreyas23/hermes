import { startServer, startBrowser, makeChecker, sleep } from './harness.mjs';

const PORT = 5198;

const { server, base } = await startServer(PORT);
const { browser, page, errors } = await startBrowser(base);
const { check, summary } = makeChecker();

try {
  // 1. Import text via API, then wait for the sidebar to reflect it.
  await page.evaluate(() => fetch('/api/import/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'E2E Text Item', text: 'First sentence here. Second sentence here.' }),
  }).then(r => r.json()));

  // The direct API import doesn't trigger a frontend refresh, so reload to
  // re-fetch the library into the sidebar.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(
    () => [...document.querySelectorAll('.item__title')].some(e => e.textContent.trim() === 'E2E Text Item'),
    { timeout: 10000 },
  );
  check('imported text item appears in sidebar',
    await page.locator('.item__title', { hasText: 'E2E Text Item' }).count() > 0);

  // 2. Open the item -> reader renders with sentence spans.
  await page.locator('.item', { has: page.locator('.item__title', { hasText: 'E2E Text Item' }) }).first().click();
  await page.waitForSelector('[data-si]', { timeout: 10000 });
  check('reader renders sentence spans', await page.locator('[data-si]').count() >= 2);

  // 3. Title is correct in the sidebar.
  check('sidebar item has correct title',
    (await page.locator('.item__title', { hasText: 'E2E Text Item' }).first().textContent())?.trim() === 'E2E Text Item');

  summary(errors);
} catch (e) {
  console.error('TEST ERROR:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
  server.kill();
}
