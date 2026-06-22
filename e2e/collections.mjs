import { startServer, startBrowser, makeChecker, sleep } from './harness.mjs';

const PORT = 5191;

const setup = [
  "sents = ['First.', 'Second.']",
  "models.add_item('Item A', 'text', 'First. Second.', sents)",
  "models.add_item('Item B', 'text', 'First. Second.', sents)",
].join('\n');

const { server, base } = await startServer(PORT, setup);
const { browser, page, errors } = await startBrowser(base);
const { check, summary } = makeChecker();

const post = (url, body) => page.evaluate(([u, b]) => fetch(u, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b),
}).then(r => r.json()), [url, body]);
const del = (url) => page.evaluate((u) => fetch(u, { method: 'DELETE' }).then(r => r.json()), url);

try {
  await page.waitForSelector('.item', { timeout: 10000 });

  // 1. Create a collection.
  const created = await post('/api/collections', { name: 'My Collection' });
  const cid = created.id;
  check('collection created', typeof cid === 'number');

  // 2. Add Item A (id 1) to it.
  const added = await post(`/api/collections/${cid}/items`, { item_id: 1 });
  check('item added to collection', added.added === true);

  // 3. Click the collection in the sidebar -> only its items show.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(
    () => [...document.querySelectorAll('.nav__collection')].some(e => e.textContent.includes('My Collection')),
    { timeout: 10000 },
  );
  await page.locator('.nav__collection', { hasText: 'My Collection' }).first().click();
  await page.waitForFunction(() => document.querySelectorAll('.item').length === 1, { timeout: 10000 });
  check('collection view shows only its items', await page.locator('.item').count() === 1);
  check('collection view shows the added item',
    (await page.locator('.item__title').first().textContent())?.trim() === 'Item A');

  // 4. Remove item from collection.
  const removed = await del(`/api/collections/${cid}/items/1`);
  check('item removed from collection', removed.removed === true);

  // 5. Delete collection.
  const deleted = await del(`/api/collections/${cid}`);
  check('collection deleted', deleted.deleted === true);

  const remaining = await page.evaluate(() => fetch('/api/collections').then(r => r.json()));
  check('collection gone from list', !(remaining.collections || []).some(c => c.id === cid));

  summary(errors);
} catch (e) {
  console.error('TEST ERROR:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
  server.kill();
}
