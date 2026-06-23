import json
import os
import queue
import re
import sqlite3
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from pysbd import Segmenter

from audio import cancel_generation, generate_audio_background, is_generating
from discovery import fetch_entries, load_feed, search_wikipedia
from extractors import (
    SUPPORTED_EXTENSIONS,
    _is_safe_url,
    clean_html_for_reader,
    extract_with_images,
    inject_sentence_spans,
    map_images_to_sentences,
)
from models import (
    BUILTIN_DESIGNS,
    add_bookmark,
    add_feed,
    add_item,
    add_to_collection,
    add_watch_folder,
    close_db,
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
    get_custom_themes,
    get_feeds,
    get_in_progress,
    get_item,
    get_items,
    get_recent,
    get_setting,
    get_watch_folders,
    init_db,
    item_audio_dir,
    item_images_dir,
    item_master_m4a,
    item_master_wav,
    remove_from_collection,
    remove_watch_folder,
    reset_item_audio,
    search_items,
    set_audio_requested,
    set_setting,
    switch_library,
    update_bookmark_note,
    update_item_content,
    update_progress,
    update_watch_folder_scanned,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
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
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
    engine_override = data.get("engine")
    _start_generation(item_id, item["sentences"], engine_override=engine_override)
    return jsonify({"generating": True, "item_id": item_id})


@app.route("/api/library/<int:item_id>/regenerate", methods=["POST"])
def library_regenerate(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    if is_generating(item_id):
        return jsonify({"error": "Already generating"}), 400
    import shutil

    audio_dir = item_audio_dir(item_id)
    if os.path.isdir(audio_dir):
        shutil.rmtree(audio_dir)
    reset_item_audio(item_id)

    sentences = item["sentences"]
    re_extracted = _re_extract(item)
    if re_extracted:
        sentences = re_extracted["sentences"]
        update_item_content(
            item_id,
            text_content=re_extracted["text"],
            sentences=sentences,
            reader_html=re_extracted.get("reader_html"),
            toc=re_extracted.get("toc"),
            images=re_extracted.get("images"),
        )

    data = request.get_json(silent=True) or {}
    engine_override = data.get("engine") or item.get("tts_engine")
    _start_generation(item_id, sentences, engine_override=engine_override)
    return jsonify({"generating": True, "item_id": item_id, "re_extracted": bool(re_extracted)})


@app.route("/api/library/<int:item_id>/clear-audio", methods=["POST"])
def library_clear_audio(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    if is_generating(item_id):
        cancel_generation(item_id)
    import shutil

    audio_dir = item_audio_dir(item_id)
    if os.path.isdir(audio_dir):
        shutil.rmtree(audio_dir)
    reset_item_audio(item_id)
    return jsonify({"cleared": True, "item_id": item_id})


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


def _do_import_file(file_path, original_path=None, title=None):
    """Extract text from a local file and create a library item.

    Returns (item_id, title, sentence_count).
    Raises ValueError if extraction fails.
    """
    import uuid

    if title is None:
        title = Path(file_path).stem

    placeholder = f"tmp_{uuid.uuid4().hex[:12]}"
    img_dir = item_images_dir(placeholder)
    os.makedirs(img_dir, exist_ok=True)

    try:
        result = extract_with_images(file_path, img_dir)
        if not result or not result["text"].strip():
            raise ValueError("Could not extract text")

        text = result["text"]
        sentences = _split(text)
        if not sentences:
            raise ValueError("No extractable text")
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
            original_path=original_path or file_path,
            images=images,
            reader_html=reader_html,
            toc=toc,
        )

        real_img_dir = item_images_dir(item_id)
        if img_dir != real_img_dir:
            if os.path.isdir(img_dir) and os.listdir(img_dir):
                os.makedirs(real_img_dir, exist_ok=True)
                for fname in os.listdir(img_dir):
                    os.rename(os.path.join(img_dir, fname), os.path.join(real_img_dir, fname))
            _rmdir_safe(img_dir)
    except Exception:
        _rmdir_safe(img_dir)
        raise

    return item_id, title, len(sentences)


@app.route("/api/import/file", methods=["POST"])
def import_file():
    body = request.get_json(silent=True) or {}
    file_path = body.get("path", "")
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404

    if not body.get("force"):
        existing = find_duplicate(original_path=file_path)
        if existing:
            return jsonify({"error": "duplicate", "existing": existing}), 409

    try:
        item_id, title, count = _do_import_file(file_path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"item_id": item_id, "title": title, "sentence_count": count})


@app.route("/api/import/upload", methods=["POST"])
def import_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp)
        tmp_path = tmp.name
    try:
        title = Path(file.filename).stem
        item_id, title, count = _do_import_file(tmp_path, title=title)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        os.unlink(tmp_path)

    return jsonify({"item_id": item_id, "title": title, "sentence_count": count})


@app.route("/api/import/url", methods=["POST"])
def import_url():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if not body.get("force"):
        existing = find_duplicate(source_url=url)
        if existing:
            return jsonify({"error": "duplicate", "existing": existing}), 409

    import tempfile
    import urllib.request

    if not _is_safe_url(url):
        return jsonify({"error": "URL blocked: private or internal address"}), 400

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
    data = request.get_json(silent=True) or {}
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
    folder = (request.get_json(silent=True) or {}).get("folder", "")
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
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
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
    body = request.get_json(silent=True) or {}
    sentence_index = body.get("sentence_index")
    if sentence_index is None:
        return jsonify({"error": "No sentence_index provided"}), 400
    bid = add_bookmark(item_id, int(sentence_index), body.get("quote"), body.get("note"))
    return jsonify({"id": bid})


@app.route("/api/bookmarks/<int:bookmark_id>", methods=["PATCH"])
def patch_bookmark(bookmark_id):
    body = request.get_json(silent=True) or {}
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
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
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
    item_id = (request.get_json(silent=True) or {}).get("item_id")
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


_ALLOWED_SETTINGS = {
    "tts_engine",
    "edge_voice",
    "say_voice",
    "kokoro_voice",
    "kokoro_model",
    "kokoro-mlx_voice",
    "piper_voice",
    "theme",
    "design",
    "skip_interval",
    "default_speed",
    "reader_font_size",
    "reader_line_height",
    "reader_max_width",
    "audio_bitrate",
    "watch_interval",
    "sentence_pause_ms",
    "save_interval",
    "auto_scroll",
}


@app.route("/api/settings", methods=["POST"])
def settings_update():
    data = request.get_json(silent=True) or {}
    for key, value in data.items():
        if key in _ALLOWED_SETTINGS:
            set_setting(key, value)
    return jsonify(get_all_settings())


# --- Themes ---


@app.route("/api/themes", methods=["GET"])
def list_themes():
    return jsonify({"themes": BUILTIN_DESIGNS + get_custom_themes()})


@app.route("/api/themes/<name>/theme.css")
def theme_css(name):
    import models as _m

    theme_dir = os.path.realpath(os.path.join(_m.THEMES_DIR, name))
    if not theme_dir.startswith(os.path.realpath(_m.THEMES_DIR) + os.sep):
        return jsonify({"error": "Invalid path"}), 403
    css_path = os.path.join(theme_dir, "theme.css")
    if not os.path.isfile(css_path):
        return jsonify({"error": "Theme not found"}), 404
    return send_file(css_path, mimetype="text/css")


# --- Watch folders ---


@app.route("/api/watch-folders", methods=["GET"])
def list_watch_folders():
    return jsonify({"folders": get_watch_folders()})


@app.route("/api/watch-folders", methods=["POST"])
def add_watch_folder_route():
    path = (request.get_json(silent=True) or {}).get("path", "").strip()
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 404
    try:
        fid = add_watch_folder(path)
    except Exception:
        return jsonify({"error": "Folder already watched"}), 409
    return jsonify({"id": fid, "path": path})


@app.route("/api/watch-folders/<int:folder_id>", methods=["DELETE"])
def delete_watch_folder(folder_id):
    remove_watch_folder(folder_id)
    return jsonify({"deleted": True})


def _watch_folder_scanner():
    time.sleep(10)
    while True:
        try:
            folders = get_watch_folders()
            for folder in folders:
                path = folder["path"]
                if not os.path.isdir(path):
                    continue
                for f in sorted(Path(path).iterdir()):
                    if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    if find_duplicate(original_path=str(f)):
                        continue
                    try:
                        item_id, title, _ = _do_import_file(str(f))
                        broadcast_sse("watch_folder_import", {"item_id": item_id, "title": title})
                    except Exception:
                        pass
                update_watch_folder_scanned(folder["id"])
        except Exception:
            pass
        try:
            interval = int(get_setting("watch_interval") or 30)
        except (TypeError, ValueError):
            interval = 30
        time.sleep(interval)


@app.route("/api/voices", methods=["GET"])
def voices_list():
    from engines import get_engine

    engine = request.args.get("engine", "edge")
    return jsonify({"voices": get_engine(engine).list_voices()})


# --- Stats & cache ---


@app.route("/api/stats", methods=["GET"])
def stats():
    import models as _m

    with _m.get_db() as db:
        items = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        audio_items = db.execute("SELECT COUNT(*) FROM items WHERE audio_ready = 1").fetchone()[0]
        dur_ms = db.execute("SELECT COALESCE(SUM(total_duration_ms), 0) FROM items WHERE audio_ready = 1").fetchone()[0]
        bookmarks = db.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
        feeds = db.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
        collections = db.execute("SELECT COUNT(*) FROM collections").fetchone()[0]

    audio_bytes = _dir_size(_m.AUDIO_DIR)
    models_dir = os.path.join(_m.LIBRARY_DIR, "models")
    models_bytes = _dir_size(models_dir)
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub")
    hf_bytes = _dir_size(hf_cache)

    return jsonify(
        {
            "items": items,
            "audio_items": audio_items,
            "total_duration_ms": dur_ms,
            "bookmarks": bookmarks,
            "feeds": feeds,
            "collections": collections,
            "audio_cache_bytes": audio_bytes,
            "models_cache_bytes": models_bytes,
            "hf_cache_bytes": hf_bytes,
        }
    )


@app.route("/api/cache/clear", methods=["POST"])
def cache_clear():
    import shutil

    import models as _m

    data = request.get_json(silent=True) or {}
    target = data.get("target")
    models_dir = os.path.join(_m.LIBRARY_DIR, "models")
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub")

    if target == "models":
        if os.path.isdir(models_dir):
            shutil.rmtree(models_dir)
            os.makedirs(models_dir, exist_ok=True)
        return jsonify({"cleared": "models"})
    elif target == "hf":
        if os.path.isdir(hf_cache):
            shutil.rmtree(hf_cache)
        return jsonify({"cleared": "hf"})
    else:
        return jsonify({"error": "Unknown target"}), 400


def _dir_size(path):
    total = 0
    if not os.path.isdir(path):
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def _checkpoint_wal(lib_dir):
    db_file = os.path.join(lib_dir, "library.db")
    if not os.path.isfile(db_file):
        return
    try:
        conn = sqlite3.connect(db_file)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except sqlite3.Error:
        pass


# --- Library path ---


@app.route("/api/library-path", methods=["GET"])
def library_path_get():
    import models

    return jsonify({"path": models.LIBRARY_DIR})


@app.route("/api/library-path", methods=["POST"])
def library_path_change():
    import shutil

    import models

    data = request.get_json(silent=True) or {}
    new_path = data.get("path", "").strip()
    mode = data.get("mode", "switch")

    if mode not in ("copy", "move", "switch"):
        return jsonify({"error": "Invalid mode"}), 400

    if not new_path:
        return jsonify({"error": "Path is required"}), 400

    new_path = os.path.expanduser(new_path)
    new_path = os.path.abspath(new_path)

    old_path = models.LIBRARY_DIR

    if os.path.normpath(new_path) == os.path.normpath(old_path):
        return jsonify({"error": "Already using this library location"}), 400

    if mode in ("copy", "move") and not os.path.isdir(old_path):
        return jsonify({"error": "Current library not found"}), 400

    parent = os.path.dirname(new_path)
    if not os.path.isdir(parent):
        return jsonify({"error": "Parent directory does not exist"}), 400

    try:
        os.makedirs(new_path, exist_ok=True)
        test_file = os.path.join(new_path, ".hermes_write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.unlink(test_file)
    except OSError:
        return jsonify({"error": "Cannot write to destination"}), 400

    if mode in ("copy", "move"):
        close_db()
        _checkpoint_wal(old_path)
        entries = [e for e in os.listdir(old_path) if not e.endswith(("-wal", "-shm", "-journal"))]
        total = len(entries)
        broadcast_sse("library_transfer", {"status": "started", "mode": mode, "total": total, "done": 0})
        try:
            for i, name in enumerate(entries):
                src = os.path.join(old_path, name)
                dst = os.path.join(new_path, name)
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    else:
                        os.unlink(dst)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                broadcast_sse(
                    "library_transfer",
                    {
                        "status": "progress",
                        "mode": mode,
                        "done": i + 1,
                        "total": total,
                        "name": name,
                    },
                )
            if mode == "move":
                shutil.rmtree(old_path)
            broadcast_sse("library_transfer", {"status": "completed", "mode": mode})
        except Exception as e:
            broadcast_sse("library_transfer", {"status": "error", "message": str(e)})
            if mode == "move":
                switch_library(new_path)
                broadcast_sse("library_changed", {"path": new_path})
                return jsonify({"error": f"Transfer partially failed: {e}", "path": new_path}), 500
            return jsonify({"error": f"Transfer failed: {e}"}), 500

    switch_library(new_path)
    broadcast_sse("library_changed", {"path": new_path})
    return jsonify({"path": new_path, "mode": mode})


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


def _re_extract(item):
    """Re-extract text from the original source. Returns dict with updated
    fields or None if re-extraction isn't possible."""
    import tempfile
    import urllib.request

    source_url = item.get("source_url")
    original_path = item.get("original_path")

    if original_path and os.path.isfile(original_path):
        img_dir = item_images_dir(item["id"])
        os.makedirs(img_dir, exist_ok=True)
        result = extract_with_images(original_path, img_dir)
        if not result or not result["text"].strip():
            return None
        text = result["text"]
        sentences = _split(text)
        if not sentences:
            return None
        images = map_images_to_sentences(result.get("images", []), text, sentences)
        reader_html = result.get("reader_html")
        toc = result.get("toc")
        if reader_html:
            reader_html = inject_sentence_spans(reader_html, sentences)
        return {"text": text, "sentences": sentences, "reader_html": reader_html, "toc": toc, "images": images}

    if source_url and _is_safe_url(source_url):
        try:
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            req = urllib.request.Request(source_url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                raw_bytes = resp.read(50 * 1024 * 1024 + 1)
        except Exception:
            return None

        is_pdf = "application/pdf" in content_type or source_url.lower().split("?")[0].endswith(".pdf")
        if is_pdf:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            try:
                img_dir = item_images_dir(item["id"])
                os.makedirs(img_dir, exist_ok=True)
                result = extract_with_images(tmp_path, img_dir)
                if not result or not result["text"].strip():
                    return None
                text = result["text"]
                sentences = _split(text)
                if not sentences:
                    return None
                images = map_images_to_sentences(result.get("images", []), text, sentences)
                reader_html = result.get("reader_html")
                toc = result.get("toc")
                if reader_html:
                    reader_html = inject_sentence_spans(reader_html, sentences)
                return {"text": text, "sentences": sentences, "reader_html": reader_html, "toc": toc, "images": images}
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

        reader_html, _title = clean_html_for_reader(downloaded, source_url)
        if not reader_html or not reader_html.strip():
            return None

        from bs4 import BeautifulSoup

        text = _html_to_text(BeautifulSoup(reader_html, "html.parser"))
        if not text.strip():
            return None
        sentences = _split(text)
        if not sentences:
            return None
        reader_html = inject_sentence_spans(reader_html, sentences)
        return {"text": text, "sentences": sentences, "reader_html": reader_html}

    return None


def _start_generation(item_id, sentences, engine_override=None):
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

    engine = engine_override or get_setting("tts_engine")
    voice = get_setting(f"{engine}_voice")
    model = get_setting("kokoro_model") if engine == "kokoro" else None
    generate_audio_background(
        item_id, sentences, on_progress, on_complete, on_cancel, engine=engine, voice=voice, model=model
    )


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
    threading.Thread(target=_watch_folder_scanner, daemon=True).start()
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
