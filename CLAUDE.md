# Hermes

Private, local-first information hub for macOS. Converts documents, articles, and live news feeds into audio you can absorb while working — with a teleprompter UI, smart library management, and podcast-style playback controls.

## Product vision

Hermes is a **productive information hub**, not just a document reader. The goal is to be the best way to passively absorb information while working — privacy-first, desktop-native, and structure-aware.

**Differentiators vs cloud listeners (ElevenReader, etc.):**
- **Privacy** — fully local, no cloud, no subscriptions, no data leaves the machine. Safe for sensitive/work/legal/medical documents.
- **Document intelligence** — structured extraction (TOC, headings, chapters), not flat text. Skip sections, navigate by chapter.
- **Desktop workflow integration** — global media keys, menu bar presence, watch folders. Lives where knowledge workers already are.
- **Active reading hybrid** — teleprompter syncs reading with listening for comprehension. Annotate, bookmark, export highlights.
- **Information aggregation** — RSS feeds, news sources, and article subscriptions feed into a single listening queue.
- **Outlook email integration** — read emails and newsletters as audio (planned).
- **Smart curation** — collections, auto-tagging, daily briefings, priority queuing.

## Git conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `style:`, `docs:`, `chore:`)
- Keep commits small and isolated — one logical change per commit
- Author: `shreyas23 <shreyas.niradi@gmail.com>`

## Architecture

- **Backend:** Python + Flask (port 5123)
- **Window:** PyWebView (native macOS WebKit, not Electron)
- **TTS:** macOS `say -o` generates per-sentence WAV files, concatenated into a cached master WAV per item
- **Storage:** SQLite at `~/hermes-library/library.db`, audio cache at `~/hermes-library/audio/<item_id>/master.wav`
- **Sentence splitting:** pysbd
- **Frontend:** Vanilla HTML/CSS/JS, SSE for real-time updates

## Key files

- `app.py` — Flask routes + PyWebView entry point
- `models.py` — SQLite schema and queries (items, progress, collections, feeds, bookmarks)
- `audio.py` — TTS generation, WAV concatenation, caching
- `extractors.py` — Text extraction (PDF via pymupdf4llm, DOCX via python-docx, HTML via bs4, RTF via striprtf, MD/TXT built-in); Wikipedia citation/appendix stripping
- `discovery.py` — Article discovery: Wikipedia search + RSS/Atom feed aggregation
- `static/js/app.js` — Frontend: init, item opening, SSE events
- `static/js/reader-highlight.js` — Reader view rendering, sentence highlighting, TOC panel
- `static/js/player.js` — Audio playback, scrubber, progress saving, media-key (Media Session) integration
- `static/js/queue.js` — Play queue: add/remove items, auto-advance on track end, queue panel UI
- `static/js/sleep-timer.js` — Sleep timer: countdown or end-of-item pause, dropdown UI
- `static/js/search.js` — Find-in-transcript (highlight matches, step through)
- `static/js/bookmarks.js` — Bookmarks & annotations panel
- `static/js/discover.js` — Discover modal: Wikipedia search + feed subscriptions
- `static/js/sidebar.js` — Library sidebar, item list, navigation
- `static/js/drag-drop.js` — Drag-and-drop file import (overlay UI, multipart upload)
- `static/js/settings.js` — Settings modal logic, design/theme switching, watch folder management
- `static/js/confirm-modal.js` — Reusable promise-based confirmation modal
- `static/css/tokens.css` — Design tokens (colors, spacing, typography, glass tokens, accent glows)
- `static/css/layout.css` — App shell layout (sidebar, main area)
- `static/css/components.css` — Component styles (reader, controls, TOC, tables, discover, bookmarks, search)
- `static/css/designs.css` — Design variant overrides (Glass, Soft Aurora); glass tokens are the base in tokens.css, `ink` is the default design
- `templates/index.html` — Main HTML layout

## Storage layout

All user data lives under `~/hermes-library/`:

```
~/hermes-library/
  library.db                # SQLite database (items, progress, collections)
  audio/
    <item_id>/
      master.wav            # Concatenated audio (22050Hz mono 16-bit PCM)
  themes/
    <theme-name>/
      manifest.json         # { "name", "version", "author" }
      theme.css             # CSS variable overrides
```

- **library.db** — contains item metadata (title, source_type, source_url, original_path), extracted text content, sentence arrays (JSON), timeline mappings (JSON), playback progress, collection membership, reader_html (structured HTML for PDFs/articles), toc (JSON table of contents for PDFs), feed subscriptions, and bookmarks/annotations (per-item, by sentence index).
- **audio/<item_id>/master.wav** — cached TTS audio for each item. Generated once on import, ~150MB per hour of content. During generation, temporary per-sentence WAVs (`sent_0000.wav`, etc.) are created in the same directory and deleted after concatenation.
- Original files are NOT copied into the library — only extracted text is stored in the database.

## Running

```
cd ~/hermes && uv run python app.py
```

## Import flow

1. User imports via URL, file path, folder scan, pasted text, drag-and-drop (multipart upload via `/api/import/upload`), or auto-import from watch folders (background scanner, 30s interval)
2. Text extracted → split into sentences → stored in SQLite
3. **PDFs:** pymupdf4llm extracts structured markdown using `TocHeaders` for heading hierarchy from PDF bookmarks. Markdown is cleaned (TOC pages stripped, page footers removed, bold-only lines matching TOC entries promoted to headings), converted to HTML via the `markdown` library, and table rows/columns are merged to fix pymupdf4llm's cell-splitting artifacts. The result is stored as `reader_html` with a navigable `toc` (JSON array of `{level, title, id}` entries). Table rendering is controlled by the `pdf_tables` setting (default: `off`).
4. **URLs:** readability extracts article HTML, cleaned and stored as `reader_html`
5. Background thread generates per-sentence audio, concatenates into master file
6. SSE broadcasts generation progress to frontend
7. Once complete, audio is cached — subsequent plays are instant with native scrubbing

## Playback

- Single cached WAV file per item — HTML5 Audio with native seeking
- Teleprompter syncs via sentence→timestamp mapping stored in the timeline
- Speed control via `audio.playbackRate` (0.5x–2x)
- Progress saved every 30s, on pause, on stop, on item switch, on window close
- Global media keys via the Media Session API — macOS routes play/pause/skip to the app (and shows Now Playing) while audio is playing, even when Hermes isn't focused
- **Play queue** — line up items to play back-to-back. Right-click sidebar items → "Play Next" (inserts at front) or "Add to Queue" (appends). Auto-advances when current item finishes. Queue is ephemeral (session-only, not persisted to DB). Queue panel toggles from the list icon in the controls status bar.
- **Sleep timer** — auto-pause after a set duration. Options: 15/30/45/60 min or "End of item" (pauses when current track finishes, preventing queue advance). Moon icon in controls status bar; click when active to cancel. Countdown displays next to the icon.

## Dependencies

Managed via `uv`. Key deps: flask, pywebview, pymupdf, pymupdf4llm, markdown, python-docx, beautifulsoup4, striprtf, pysbd, trafilatura.

Note: system pip/pip3 have a broken expat library on this machine — always use `uv` for dependency management.

## Design system

The UI supports multiple visual designs, switchable via Settings > Design. The system is token-based — component CSS references design tokens (`--glass-bg`, `--accent-glow`, `--glass-blur`, etc.) and never contains design-specific values.

**Current designs:**
- `ink` (default) — monochromatic (accent = text color), opaque surfaces, no blur/glow, minimal shadows
- `glass` — frosted translucency, backdrop-blur, Apple blue accent
- `aurora` — lavender accent, warm-to-cool gradient body, tinted glass, rounder corners

**Default design** is configured in one place — `models.DEFAULTS['design']`. The index route templates it into `index.html` (`window.__DEFAULT_DESIGN`, used by the `<head>` script before paint) and `/api/settings` serves it to `settings.js`, so changing that one value updates the default everywhere.

**How it works:** Each design is a `[data-design="..."]` CSS selector block in `designs.css` that overrides tokens from `tokens.css`. Glass tokens are the base layer in `tokens.css` (so other designs only override what differs); `ink` is the default *selected* design. Light/dark variants use `[data-design="..."][data-theme="dark"]` selectors. The `data-design` attribute is set on `<html>`, initialized from localStorage (falling back to the templated default) in the `<head>` script, and persisted to both localStorage and SQLite on change.

**Adding a built-in design:**
1. Add a token override block to `static/css/designs.css` (light + dark variants)
2. Add an entry to `BUILTIN_DESIGNS` in `models.py`
3. Key tokens to override: `--accent`, `--glass-bg`, `--glass-blur` (set to `blur(0px)` for opaque), `--glass-border`, `--glass-shadow`, `--accent-glow` (set to `none` to disable), `--radius-md`/`--radius-lg`, `--shadow-*`, plus body background and reading highlight via element selectors

**Custom themes (user-importable, Obsidian-style):**

Users can add themes by placing a folder in `~/hermes-library/themes/`:

```
~/hermes-library/themes/
  my-theme/
    manifest.json    # { "name": "My Theme", "version": "1.0", "author": "..." }
    theme.css        # [data-design="my-theme"] { --accent: ...; ... }
```

- `manifest.json` must have at least a `name` field. `version` and `author` are optional.
- `theme.css` uses the same `[data-design="<folder-name>"]` selector convention as built-in designs. Must provide both light and dark variants.
- Themes appear in Settings > Design alongside built-ins. CSS is loaded dynamically via `/api/themes/<name>/theme.css`.
- The `<head>` script injects a blocking `<link>` for custom themes before first paint (no flash).
- API: `GET /api/themes` returns all themes (built-in + custom). `GET /api/themes/<name>/theme.css` serves custom theme CSS.

## Settings

Stored in SQLite `settings` table. Key settings:
- `design` — `ink` (default), `glass`, or `aurora` (plus custom themes)
- `tts_engine` — `edge` (default) or `say`
- `edge_voice` / `say_voice` — voice selection per engine
- `pdf_tables` — `off` (default) disables HTML table rendering in PDFs; set to `on` to enable (tables are often broken by pymupdf4llm's cell-splitting)
- `skip_interval` — skip forward/back seconds (`15` default, range 5–60)
- `default_speed` — initial playback speed (`1` default, one of 0.5/0.75/1/1.25/1.5/2)
- `auto_scroll` — whether reader auto-follows playback (`on` default)
- `reader_font_size` — reader text size in px (`15` default, range 12–24)
- `reader_line_height` — reader line spacing (`1.8` default, range 1.2–2.4)
- `reader_max_width` — reader content width in px (`720` default, range 500–1200)
- `audio_bitrate` — AAC export bitrate (`64000` default, options: 32000/64000/96000/128000)
- `sentence_pause_ms` — silence between sentences in ms (`100` default, range 0–500)
- `watch_interval` — watch folder scan interval in seconds (`30` default, range 10–300)
- `save_interval` — progress auto-save interval in ms (`30000` default, range 5000–120000)

## Future development

Ordered by dependency and impact — each tier makes the product meaningfully better for current users before expanding scope.

**Shipped:** Discover (Wikipedia search + RSS/Atom & Substack feed subscriptions), opt-in audio generation with cancel/retry, global media keys (Media Session API), search within transcript, bookmarks & annotations, play queue (session-only, auto-advance, "Play Next" / "Add to Queue" via right-click), sleep timer (timed or end-of-item), drag-and-drop import (multipart upload), watch folders (background scanner every 30s, managed in Settings), teleprompter mode (immersive centered-sentence view, toggle via T key or toolbar button).

**1. Capture & export** — close the loop on the comprehension tools we just shipped
- **Export highlights** — export stored bookmarks & annotations (Markdown/file); builds directly on the `bookmarks` table

**2. Audio quality** — voice quality is the single biggest factor in whether someone keeps listening
- **Kokoro TTS** — Kokoro-82M runs locally on Apple Silicon with near-cloud quality. Eliminates the need for cloud TTS while keeping everything private. Multiple voices, fast inference via `kokoro-onnx`.
- **OpenAI TTS** — optional cloud fallback for users who want the highest fidelity and don't mind API calls

**3. Content expansion** — feeds are subscribable today; this makes them proactive
- **Browser extension** — Safari/Chrome extension with a "Send to Hermes" button. Sends the current page URL to the local Flask API (`/api/import/url`) for extraction and import. One-click capture without switching windows.
- **Background feed sync** — periodically pull new entries from subscribed feeds into the library (currently entries are fetched on-demand in Discover)
- **Daily briefing** — auto-queue unread items by priority each morning (depends on play queue)

**4. Reading statistics** — no competitor does this; ElevenReader has zero analytics
- **Stats page** — listening time (daily/weekly/all-time), items completed, streak tracking, average session length
- **Per-item stats** — time spent, % completed, replay count
- **Genre/source breakdown** — listening distribution across source types (PDF, article, feed, text) and collections

**5. Polish & export**
- **Inline images in transcript** — display images from articles/PDFs/DOCX in the teleprompter view, positioned between sentences where they appeared in the original. Caption/alt-text reading as a follow-on.
- **PDF table improvements** — pymupdf4llm splits multi-line PDF cells into extra rows/columns; current post-processing merges them but results are imperfect. `pdf_tables` setting defaults to `off` until quality improves.
- **Auto-tagging** — tag items by topic automatically
- **Smart collections** — dynamic collections based on filters/rules
- **Speed-specific audio caching** — pre-generate audio at different speeds (currently speed is applied via playbackRate which changes pitch slightly)
- **Export as podcast MP3** — export library items as MP3 files with metadata

## Testing

Two test layers, each runnable with one command:

```
uv run pytest              # Python unit + integration tests (<1s)
npm run e2e:all            # All Playwright E2E tests (~2min)
```

The pre-commit hook runs ruff + pytest on every commit. CI (`.github/workflows/test.yml`) runs both layers on every push/PR.

### Python tests (pytest)

Tests live in `tests/`. `conftest.py` provides shared fixtures:

- **`isolated_db` (autouse)** — every test gets a fresh SQLite in a temp dir. Overrides `models.LIBRARY_DIR`, `DB_PATH`, `AUDIO_DIR`, `IMAGES_DIR`. No setup needed.
- **`client`** — Flask `test_client()` with isolated DB ready.
- **`sample_item`** — pre-seeded 3-sentence text item, returns `(item_id, sentences)`.
- **`audio_ready_item`** — extends `sample_item` with synthetic silent WAV + timeline.

| File | What it covers |
|------|---------------|
| `test_models.py` | Item CRUD, cascading deletes, progress upsert, search escaping, collections, feeds, bookmarks |
| `test_extractors.py` | `_is_safe_url` SSRF guard, `inject_sentence_spans`, `clean_html_for_reader`, image-to-sentence mapping |
| `test_routes.py` | API integration: imports, progress, bookmarks, audio serving, path traversal, settings |
| `test_audio.py` | WAV concatenation, silence padding, partial cleanup |
| `test_discovery.py` | `strip_html`, feed entry normalization |

To add a test: create a function in the right `tests/test_*.py` file, use any fixture from conftest, run `uv run pytest tests/test_file.py::test_name`.

### E2E tests (Playwright)

Scripts live in `e2e/`. Each test starts its own Flask server on an isolated temp DB (never touches `~/hermes-library`). The shared `e2e/harness.mjs` handles server lifecycle, browser setup, and assertions.

| Script | Port | What it covers |
|--------|------|---------------|
| `bookmarks.mjs` | 5193 | Add/persist/jump/delete bookmark, annotations |
| `search.mjs` | 5194 | Find-in-transcript: highlighting, next/prev/wrap |
| `media-keys.mjs` | 5195 | Media Session handler registration, metadata |
| `discover.mjs` | 5196 | Wikipedia search, import, feeds tab, pending UI |
| `screenshot.mjs` | 5197 | Visual smoke: empty, item open, playing states |
| `import.mjs` | 5198 | Text import, sidebar rendering, sentence spans |
| `collections.mjs` | 5191 | Create/add/view/remove/delete collections |
| `queue-timer.mjs` | 5199 | Play queue and sleep timer |

To add an E2E test: create a new `.mjs` file, import from `harness.mjs`, pick an unused port, add it to `e2e:all` in `package.json`.

### E2E rules

- **Screenshot after every UI change.** Before reporting a visual change as done, run `node e2e/screenshot.mjs` and read the screenshots. Don't ship layout you haven't seen.
- **Each test gets its own port.** Never connect to the user's running app on 5123.
- **Use `domcontentloaded`, not `networkidle`.** The SSE endpoint keeps connections open — `networkidle` will timeout.
- **Prefer `waitForSelector`/`waitForFunction` over `sleep()`.** Hardcoded sleeps are flaky.
- **Screenshots go in `e2e/screenshots/`.** This directory is gitignored. Name files with numbered prefixes: `01-empty.png`, `02-item-open.png`, etc.
- **Audio is opt-in — pick audio-ready items for playback tests.** Imports no longer auto-generate audio; new items are `pending` (sidebar shows a status badge, the reader shows a Generate-audio bar, transport controls are hidden). To test playback, select an item with audio (`.item:not(:has(.badge))`) or generate audio first. Use an isolated temp library (override `models.DB_PATH`/`AUDIO_DIR`/`IMAGES_DIR` before `from app import app`) for feature tests so the real library is untouched.

### What to test

**UX / visual regression:** screenshot each app state (empty, item open, playing, browsing while playing) and compare before/after. Check all three designs (glass, aurora, ink) and both themes (light, dark) when touching CSS.

**Frontend:** verify controls show/hide correctly, scrubber updates during playback, sentence highlighting syncs, keyboard shortcuts work, imports complete and appear in sidebar.

**Backend:** use `curl` or `fetch()` against the API endpoints (`/api/library`, `/api/library/<id>`, `/api/import/*`, `/api/library/<id>/progress`) to verify responses. Check that audio files exist after import completes.

**Bugs / regression:** write a targeted Playwright script in `e2e/` that reproduces the bug scenario, verify the fix, keep the script if the scenario is worth protecting.
