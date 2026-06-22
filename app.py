import json
import os
import queue
import re
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from pysbd import Segmenter

from audio import cancel_generation, generate_audio_background, is_generating
from discovery import fetch_entries, load_feed, search_wikipedia
from extractors import (
    SUPPORTED_EXTENSIONS,
    clean_html_for_reader,
    extract_with_images,
    inject_sentence_spans,
    map_images_to_sentences,
)
from models import (
    add_bookmark,
    add_feed,
    add_item,
    add_to_collection,
    create_collection,
    delete_bookmark,
    delete_collection,
    delete_feed,
    delete_item,
    find_duplicate,
    find_feed,
    get_all_settings,
    get_bookmarks,
    get_collections,
    get_feeds,
    get_in_progress,
    get_item,
    get_items,
    get_recent,
    get_setting,
    init_db,
    item_images_dir,
    item_master_m4a,
    item_master_wav,
    remove_from_collection,
    search_items,
    set_audio_requested,
    set_setting,
    update_bookmark_note,
    update_progress,
)

app = Flask(__name__)
segmenter = Segmenter(language="en", clean=False)

sse_queues: list[queue.Queue] = []
sse_lock = threading.Lock()


def broadcast_sse(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_queues.remove(q)


@app.route("/")
def index():
    # default_design comes from the central config (models.DEFAULTS) unless overridden in settings
    return render_template("index.html", default_design=get_setting("design"))


# --- Library endpoints ---


@app.route("/api/library", methods=["GET"])
def library_list():
    view = request.args.get("view", "recent")
    source_type = request.args.get("source_type")
    collection_id = request.args.get("collection_id", type=int)

    if view == "recent":
        items = get_recent()
    elif view == "in_progress":
        items = get_in_progress()
    elif view == "collection" and collection_id:
        items = get_items(collection_id=collection_id)
    elif source_type:
        items = get_items(source_type=source_type)
    else:
        items = get_items()

    return jsonify({"items": [_item_summary(i) for i in items]})


@app.route("/api/library/search", methods=["GET"])
def library_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"items": []})
    items = search_items(query)
    return jsonify({"items": [_item_summary(i) for i in items]})


@app.route("/api/library/<int:item_id>", methods=["GET"])
def library_item(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    audio_ready = bool(item["audio_ready"])
    generating = not audio_ready and is_generating(item["id"])
    requested = bool(item.get("audio_requested"))
    item["generating"] = generating
    item["pending"] = not audio_ready and not generating and not requested
    item["interrupted"] = not audio_ready and not generating and requested
    return jsonify({"item": item})


@app.route("/api/library/<int:item_id>", methods=["DELETE"])
def library_delete(item_id):
    cancel_generation(item_id, wait=True)
    delete_item(item_id)
    return jsonify({"deleted": True})


@app.route("/api/library/<int:item_id>/cancel", methods=["POST"])
def library_cancel(item_id):
    cancelled = cancel_generation(item_id, wait=True)
    set_audio_requested(item_id, False)
    broadcast_sse("generation_cancelled", {"item_id": item_id})
    return jsonify({"cancelled": cancelled})


@app.route("/api/library/<int:item_id>/progress", methods=["POST"])
def library_progress(item_id):
    data = request.json or {}
    update_progress(
        item_id,
        data.get("current_sentence", 0),
        data.get("current_time_ms", 0),
        data.get("is_finished", False),
    )
    return jsonify({"saved": True})


@app.route("/api/library/<int:item_id>/generate", methods=["POST"])
def library_generate(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    if item["audio_ready"]:
        return jsonify({"error": "Audio already generated"}), 400
    if is_generating(item_id):
        return jsonify({"error": "Already generating"}), 400
    _start_generation(item_id, item["sentences"])
    return jsonify({"generating": True, "item_id": item_id})


@app.route("/api/library/<int:item_id>/images/<path:filename>")
def library_image(item_id, filename):
    img_dir = item_images_dir(item_id)
    filepath = os.path.realpath(os.path.join(img_dir, filename))
    if not filepath.startswith(os.path.realpath(img_dir) + os.sep):
        return jsonify({"error": "Invalid path"}), 403
    if not os.path.isfile(filepath):
        return jsonify({"error": "Image not found"}), 404
    return send_file(filepath)


@app.route("/api/library/<int:item_id>/audio")
def library_audio(item_id):
    m4a_path = item_master_m4a(item_id)
    if os.path.isfile(m4a_path):
        return send_file(m4a_path, mimetype="audio/mp4")
    wav_path = item_master_wav(item_id)
    if os.path.isfile(wav_path):
        return send_file(wav_path, mimetype="audio/wav")
    return jsonify({"error": "Audio not ready"}), 404


# --- Import endpoints ---


@app.route("/api/import/file", methods=["POST"])
def import_file():
    body = request.json or {}
    file_path = body.get("path", "")
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404

    if not body.get("force"):
        existing = find_duplicate(original_path=file_path)
        if existing:
            return jsonify({"error": "duplicate", "existing": existing}), 409

    import uuid

    placeholder = f"tmp_{uuid.uuid4().hex[:12]}"
    img_dir = item_images_dir(placeholder)
    os.makedirs(img_dir, exist_ok=True)

    try:
        result = extract_with_images(file_path, img_dir)
        if not result or not result["text"].strip():
            return jsonify({"error": "Could not extract text"}), 400

        text = result["text"]
        title = Path(file_path).stem
        sentences = _split(text)
        if not sentences:
            return jsonify({"error": "No extractable text"}), 400
        images = map_images_to_sentences(result.get("images", []), text, sentences)

        reader_html = result.get("reader_html")
        toc = result.get("toc")
        if reader_html:
            reader_html = inject_sentence_spans(reader_html, sentences)

        item_id = add_item(
            title=title,
            source_type="document",
            text_content=text,
            sentences=sentences,
            original_path=file_path,
            images=images,
            reader_html=reader_html,
            toc=toc,
        )

        real_img_dir = item_images_dir(item_id)
        if img_dir != real_img_dir:
            if os.path.isdir(img_dir) and os.listdir(img_dir):
                os.makedirs(real_img_dir, exist_ok=True)
                for f in os.listdir(img_dir):
                    os.rename(os.path.join(img_dir, f), os.path.join(real_img_dir, f))
            _rmdir_safe(img_dir)
    except Exception:
        _rmdir_safe(img_dir)
        raise

    return jsonify({"item_id": item_id, "title": title, "sentence_count": len(sentences)})


@app.route("/api/import/url", methods=["POST"])
def import_url():
    body = request.json or {}
    url = body.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if not body.get("force"):
        existing = find_duplicate(source_url=url)
        if existing:
            return jsonify({"error": "duplicate", "existing": existing}), 409

    import tempfile
    import urllib.request

    MAX_DOWNLOAD = 50 * 1024 * 1024
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            raw_bytes = resp.read(MAX_DOWNLOAD + 1)
            if len(raw_bytes) > MAX_DOWNLOAD:
                return jsonify({"error": "File too large (max 50MB)"}), 400
    except Exception:
        return jsonify({"error": "Could not download page"}), 400
    if not raw_bytes:
        return jsonify({"error": "Could not download page"}), 400

    is_pdf = "application/pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")

    if is_pdf:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        try:
            import uuid

            placeholder = f"tmp_{uuid.uuid4().hex[:12]}"
            img_dir = item_images_dir(placeholder)
            os.makedirs(img_dir, exist_ok=True)

            try:
                result = extract_with_images(tmp_path, img_dir)
                if not result or not result["text"].strip():
                    return jsonify({"error": "Could not extract text from PDF"}), 400

                text = result["text"]
                title = Path(url.split("?")[0].split("/")[-1]).stem or url
                sentences = _split(text)
                if not sentences:
                    return jsonify({"error": "No extractable text"}), 400
                images = map_images_to_sentences(result.get("images", []), text, sentences)

                reader_html = result.get("reader_html")
                toc = result.get("toc")
                if reader_html:
                    reader_html = inject_sentence_spans(reader_html, sentences)

                item_id = add_item(
                    title=title,
                    source_type="document",
                    text_content=text,
                    sentences=sentences,
                    source_url=url,
                    images=images,
                    reader_html=reader_html,
                    toc=toc,
                )

                real_img_dir = item_images_dir(item_id)
                if img_dir != real_img_dir:
                    if os.path.isdir(img_dir) and os.listdir(img_dir):
                        os.makedirs(real_img_dir, exist_ok=True)
                        for f in os.listdir(img_dir):
                            os.rename(os.path.join(img_dir, f), os.path.join(real_img_dir, f))
                    _rmdir_safe(img_dir)
            except Exception:
                _rmdir_safe(img_dir)
                raise

            return jsonify({"item_id": item_id, "title": title, "sentence_count": len(sentences)})
        finally:
            os.unlink(tmp_path)

    from email.message import Message

    msg = Message()
    msg["content-type"] = content_type
    charset = msg.get_param("charset", "utf-8")
    try:
        downloaded = raw_bytes.decode(charset)
    except (UnicodeDecodeError, LookupError):
        downloaded = raw_bytes.decode("utf-8", errors="replace")

    reader_html, title = clean_html_for_reader(downloaded, url)
    title = title or url
    if not reader_html or not reader_html.strip():
        return jsonify({"error": "Could not extract article text"}), 400

    from bs4 import BeautifulSoup

    text_only = _html_to_text(BeautifulSoup(reader_html, "html.parser"))
    if not text_only.strip():
        return jsonify({"error": "Could not extract article text"}), 400

    sentences = _split(text_only)
    if not sentences:
        return jsonify({"error": "No extractable text"}), 400
    reader_html = inject_sentence_spans(reader_html, sentences)

    item_id = add_item(
        title=title,
        source_type="article",
        text_content=text_only,
        sentences=sentences,
        source_url=url,
        reader_html=reader_html,
    )

    return jsonify({"item_id": item_id, "title": title, "sentence_count": len(sentences)})


@app.route("/api/import/text", methods=["POST"])
def import_text():
    data = request.json or {}
    title = data.get("title", "Untitled").strip()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    sentences = _split(text)
    if not sentences:
        return jsonify({"error": "No extractable text"}), 400

    item_id = add_item(
        title=title,
        source_type="text",
        text_content=text,
        sentences=sentences,
    )

    return jsonify({"item_id": item_id, "title": title, "sentence_count": len(sentences)})


@app.route("/api/import/folder", methods=["POST"])
def import_folder():
    folder = (request.json or {}).get("folder", "")
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return jsonify({"error": "Not a valid directory"}), 400

    files = []
    for f in sorted(Path(folder).iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append({"name": f.name, "path": str(f), "ext": f.suffix.lower()})
            if len(files) >= 500:
                break

    return jsonify({"folder": folder, "files": files})


# --- Discovery ---


@app.route("/api/discover/wikipedia", methods=["GET"])
def discover_wikipedia():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    try:
        results = search_wikipedia(query)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 502
    return jsonify({"results": results})


@app.route("/api/feeds", methods=["GET"])
def list_feeds():
    return jsonify({"feeds": get_feeds()})


@app.route("/api/feeds", methods=["POST"])
def subscribe_feed():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No feed URL provided"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    existing = find_feed(url)
    if existing:
        return jsonify({"error": "Already subscribed", "feed": existing}), 409

    try:
        meta, _entries = load_feed(url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not load feed: {e}"}), 400

    feed_id = add_feed(meta["title"], url, meta["site_url"])
    return jsonify({"id": feed_id, "title": meta["title"]})


@app.route("/api/feeds/<int:feed_id>", methods=["DELETE"])
def unsubscribe_feed(feed_id):
    delete_feed(feed_id)
    return jsonify({"ok": True})


@app.route("/api/feeds/entries", methods=["GET"])
def feed_entries():
    return jsonify({"entries": fetch_entries(get_feeds())})


# --- Bookmarks & annotations ---


@app.route("/api/library/<int:item_id>/bookmarks", methods=["GET"])
def list_bookmarks(item_id):
    return jsonify({"bookmarks": get_bookmarks(item_id)})


@app.route("/api/library/<int:item_id>/bookmarks", methods=["POST"])
def create_bookmark(item_id):
    body = request.json or {}
    sentence_index = body.get("sentence_index")
    if sentence_index is None:
        return jsonify({"error": "No sentence_index provided"}), 400
    bid = add_bookmark(item_id, int(sentence_index), body.get("quote"), body.get("note"))
    return jsonify({"id": bid})


@app.route("/api/bookmarks/<int:bookmark_id>", methods=["PATCH"])
def patch_bookmark(bookmark_id):
    body = request.json or {}
    update_bookmark_note(bookmark_id, body.get("note", ""))
    return jsonify({"ok": True})


@app.route("/api/bookmarks/<int:bookmark_id>", methods=["DELETE"])
def remove_bookmark(bookmark_id):
    delete_bookmark(bookmark_id)
    return jsonify({"ok": True})


# --- Collections ---


@app.route("/api/collections", methods=["GET"])
def list_collections():
    return jsonify({"collections": get_collections()})


@app.route("/api/collections", methods=["POST"])
def new_collection():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    cid = create_collection(name)
    return jsonify({"id": cid, "name": name})


@app.route("/api/collections/<int:cid>", methods=["DELETE"])
def del_collection(cid):
    delete_collection(cid)
    return jsonify({"deleted": True})


@app.route("/api/collections/<int:cid>/items", methods=["POST"])
def collection_add(cid):
    item_id = (request.json or {}).get("item_id")
    add_to_collection(cid, item_id)
    return jsonify({"added": True})


@app.route("/api/collections/<int:cid>/items/<int:item_id>", methods=["DELETE"])
def collection_remove(cid, item_id):
    remove_from_collection(cid, item_id)
    return jsonify({"removed": True})


# --- Settings ---


@app.route("/api/settings", methods=["GET"])
def settings_get():
    return jsonify(get_all_settings())


_ALLOWED_SETTINGS = {"tts_engine", "edge_voice", "say_voice", "theme", "design"}


@app.route("/api/settings", methods=["POST"])
def settings_update():
    data = request.json or {}
    for key, value in data.items():
        if key in _ALLOWED_SETTINGS:
            set_setting(key, value)
    return jsonify(get_all_settings())


_edge_voices_cache = []


@app.route("/api/voices", methods=["GET"])
def voices_list():
    global _edge_voices_cache
    engine = request.args.get("engine", "edge")
    if engine == "edge":
        if not _edge_voices_cache:
            import asyncio

            import edge_tts

            loop = asyncio.new_event_loop()
            try:
                all_voices = loop.run_until_complete(edge_tts.list_voices())
            finally:
                loop.close()
            _edge_voices_cache = [
                {"id": v["ShortName"], "name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
                for v in all_voices
                if v["Locale"].startswith("en-")
            ]
        return jsonify({"voices": _edge_voices_cache})
    else:
        import subprocess

        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        voices = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "en_" in line:
                name = parts[0]
                voices.append({"id": name, "name": name, "locale": parts[1] if len(parts) > 1 else ""})
        return jsonify({"voices": voices})


# --- SSE ---


@app.route("/api/events")
def events():
    q = queue.Queue(maxsize=100)
    with sse_lock:
        sse_queues.append(q)

    def stream():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            with sse_lock:
                if q in sse_queues:
                    sse_queues.remove(q)

    return Response(
        stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# --- Helpers ---


def _rmdir_safe(path):
    if os.path.isdir(path):
        for f in os.listdir(path):
            try:
                os.unlink(os.path.join(path, f))
            except OSError:
                pass
        try:
            os.rmdir(path)
        except OSError:
            pass


_BLOCK_TAGS = frozenset(
    [
        "p",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "blockquote",
        "pre",
        "table",
        "tr",
        "td",
        "th",
        "section",
        "article",
        "figure",
        "figcaption",
        "details",
        "summary",
        "dt",
        "dd",
    ]
)


def _html_to_text(soup):
    from bs4 import NavigableString, Tag

    parts = []
    for el in soup.descendants:
        if isinstance(el, NavigableString):
            text = str(el).strip()
            if text:
                if parts and not parts[-1].endswith("\n"):
                    parts.append(" ")
                parts.append(text)
        elif isinstance(el, Tag):
            if el.name == "br":
                parts.append("\n")
            elif el.name in _BLOCK_TAGS and parts and not parts[-1].endswith("\n"):
                parts.append("\n")
    return re.sub(r"\n{2,}", "\n", "".join(parts)).strip()


def _split(text):
    sentences = segmenter.segment(text)
    return [s.strip() for s in sentences if s.strip()]


def _start_generation(item_id, sentences):
    set_audio_requested(item_id, True)

    def on_progress(done, total):
        broadcast_sse(
            "generation_progress",
            {
                "item_id": item_id,
                "done": done,
                "total": total,
            },
        )

    def on_complete(iid, timeline, total_ms):
        broadcast_sse(
            "generation_complete",
            {
                "item_id": iid,
                "total_duration_ms": total_ms,
            },
        )

    def on_cancel(iid):
        broadcast_sse("generation_cancelled", {"item_id": iid})

    engine = get_setting("tts_engine")
    voice = get_setting("edge_voice") if engine == "edge" else get_setting("say_voice")
    generate_audio_background(item_id, sentences, on_progress, on_complete, on_cancel, engine=engine, voice=voice)


def _item_summary(item):
    audio_ready = bool(item["audio_ready"])
    generating = not audio_ready and is_generating(item["id"])
    requested = bool(item["audio_requested"])
    return {
        "id": item["id"],
        "title": item["title"],
        "source_type": item["source_type"],
        "source_url": item.get("source_url"),
        "audio_ready": audio_ready,
        "generating": generating,
        "pending": not audio_ready and not generating and not requested,
        "interrupted": not audio_ready and not generating and requested,
        "total_duration_ms": item["total_duration_ms"],
        "sentence_count": len(item["sentences"]),
        "created_at": item["created_at"],
        "progress": item.get("progress"),
    }


def start_server():
    init_db()
    app.run(port=5123, threaded=True, use_reloader=False)


if __name__ == "__main__":
    import webview

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    window = webview.create_window(
        "Hermes",
        "http://127.0.0.1:5123",
        width=1100,
        height=750,
        min_size=(800, 500),
    )

    def _on_closing():
        window.hide()
        return False

    def _setup_dock_reopen():
        import time

        time.sleep(1)
        try:
            import objc
            from AppKit import NSApplication, NSImage

            ns_app = NSApplication.sharedApplication()
            delegate = ns_app.delegate()

            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.icns")
            if os.path.isfile(icon_path):
                icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
                ns_app.setApplicationIconImage_(icon)

            def _reopen(self, app, flag):
                window.show()
                return True

            objc.classAddMethod(
                delegate.__class__,
                b"applicationShouldHandleReopen:hasVisibleWindows:",
                _reopen,
            )

        except ImportError:
            pass

    window.events.closing += _on_closing
    webview.start(func=_setup_dock_reopen)
