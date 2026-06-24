import { startServer, startBrowser, sleep } from './harness.mjs';
import { execSync } from 'node:child_process';

const PORT = 5200;
const DIR = 'e2e/screenshots/demo';
execSync(`mkdir -p ${DIR}`);

const ARTICLE_SENTENCES = [
  'The most important skill you can develop is the ability to absorb information efficiently.',
  'Reading is slow — most people read at 250 words per minute, but can listen at 350.',
  'The gap between those two numbers represents hours of your week.',
  'What if you could turn every article, every PDF, every research paper into audio?',
  'Not robotic, mechanical audio — natural speech that you can listen to while walking, cooking, or commuting.',
  'This is the core idea behind a new generation of text-to-speech tools.',
  'But most of them send your documents to the cloud.',
  'Your medical records, your legal briefs, your private notes — all uploaded to someone else\'s server.',
  'There is a better way: run everything locally, on your own hardware.',
  'Modern neural TTS models are small enough to run on a laptop.',
  'Apple Silicon makes this practical — real-time speech synthesis with no internet required.',
  'The result is a private, local listening experience that rivals cloud services.',
];

const ARTICLE_HTML = '<h1>The Case for Local Text-to-Speech</h1>'
  + ARTICLE_SENTENCES.map((s, i) =>
    `<p><span data-si="${i}">${s}</span></p>`
  ).join('');

const SETUP = `
import os, wave, json, time
sentences = ${JSON.stringify(ARTICLE_SENTENCES)}
html = ${JSON.stringify(ARTICLE_HTML)}

# Main article (audio-ready)
item_id = models.add_item(
    title='The Case for Local Text-to-Speech',
    source_type='article',
    text_content=' '.join(sentences),
    sentences=sentences,
    source_url='https://example.com/local-tts',
    reader_html=html,
)
audio_dir = models.item_audio_dir(item_id)
os.makedirs(audio_dir, exist_ok=True)
wav_path = models.item_master_wav(item_id)
with wave.open(wav_path, 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    w.writeframes(b'\\x00\\x00' * 22050 * 30)
timeline = [{'index': i, 'start_ms': i * 2500, 'duration_ms': 2500} for i in range(len(sentences))]
models.update_item_audio(item_id, timeline, len(sentences) * 2500)

# Other sidebar items
for title, stype in [
    ('How to Read a Paper — S. Keshav', 'article'),
    ('Global Robotics Roadmap 2025', 'document'),
    ('Deep Learning in Practice', 'article'),
    ('Weekly AI Newsletter — June 2026', 'article'),
]:
    s = ['Placeholder sentence one.', 'Placeholder sentence two.', 'Placeholder sentence three.']
    sid = models.add_item(title=title, source_type=stype, text_content=' '.join(s), sentences=s)
    ad = models.item_audio_dir(sid)
    os.makedirs(ad, exist_ok=True)
    wp = models.item_master_wav(sid)
    with wave.open(wp, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b'\\x00\\x00' * 22050 * 5)
    tl = [{'index': i, 'start_ms': i * 1000, 'duration_ms': 1000} for i in range(3)]
    models.update_item_audio(sid, tl, 3000)

# Create a collection
models.create_collection('Research')
models.add_to_collection(models.get_collections()[0]['id'], item_id)
`;

const { server, base } = await startServer(PORT, SETUP);
const { browser, page } = await startBrowser(base, { viewport: { width: 1200, height: 800 } });

try {
  // Frame 1: Library view with items
  await sleep(800);
  await page.screenshot({ path: `${DIR}/01-library.png` });
  console.log('01 — library');

  // Frame 2: Click main article → reader opens
  await page.locator('.item', { has: page.locator('.item__title', { hasText: 'The Case for Local' }) }).first().click();
  await page.waitForSelector('[data-si]', { timeout: 10000 });
  await sleep(500);
  await page.screenshot({ path: `${DIR}/02-reader.png` });
  console.log('02 — reader');

  // Frame 3: Playing with sentence highlight visible
  const playBtn = page.locator('#btn-play');
  if (await playBtn.isVisible()) {
    await playBtn.click();
    await sleep(300);
    // Directly highlight sentence 4 ("Not robotic, mechanical audio...")
    // since seeking a silent WAV doesn't fire timeupdate reliably
    await page.evaluate(() => {
      document.querySelectorAll('[data-si]').forEach(el => el.classList.remove('is-reading'));
      const target = document.querySelector('[data-si="4"]');
      if (target) {
        target.classList.add('is-reading');
        target.scrollIntoView({ block: 'center' });
      }
    });
    await sleep(500);
    await page.screenshot({ path: `${DIR}/03-playing.png` });
    console.log('03 — playing with highlight');
  }

  // Frame 4: Teleprompter mode with sentence 3 highlighted
  const teleBtn = page.locator('#btn-teleprompter');
  if (await teleBtn.count() > 0) {
    await teleBtn.click();
    await sleep(500);
    // Apply teleprompter-style highlighting: is-reading + is-played + is-near
    await page.evaluate(() => {
      const idx = 3;
      document.querySelectorAll('[data-si]').forEach((el, i) => {
        el.classList.remove('is-reading', 'is-near', 'is-played');
        const si = parseInt(el.dataset.si);
        if (si < idx) el.classList.add('is-played');
        else if (si === idx) el.classList.add('is-reading');
        else if (Math.abs(si - idx) <= 2) el.classList.add('is-near');
      });
      const target = document.querySelector('[data-si="3"]');
      if (target) target.scrollIntoView({ block: 'center' });
    });
    await sleep(500);
    await page.screenshot({ path: `${DIR}/04-teleprompter.png` });
    console.log('04 — teleprompter');

    await teleBtn.click();
    await sleep(300);
  }

  console.log(`\nFrames saved to ${DIR}/`);
  console.log('Stitching GIF...');

  // Stitch into GIF: 2.5s per frame
  execSync([
    'magick',
    `${DIR}/01-library.png`,
    `${DIR}/02-reader.png`,
    `${DIR}/03-playing.png`,
    `${DIR}/04-teleprompter.png`,
    '-delay 250',           // 250 centiseconds = 2.5s per frame
    '-loop 0',              // infinite loop
    `${DIR}/../demo.gif`,
  ].join(' '));

  console.log('GIF created at e2e/screenshots/demo.gif');
} finally {
  await browser.close();
  server.kill();
}
