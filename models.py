import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

LIBRARY_DIR = os.path.expanduser("~/hermes-library")
DB_PATH = os.path.join(LIBRARY_DIR, "library.db")
AUDIO_DIR = os.path.join(LIBRARY_DIR, "audio")
IMAGES_DIR = os.path.join(LIBRARY_DIR, "images")

_local = threading.local()


def init_db():
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                original_path TEXT,
                text_content TEXT NOT NULL,
                sentences TEXT NOT NULL,
                timeline TEXT,
                total_duration_ms REAL DEFAULT 0,
                audio_ready INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS progress (
                item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
                current_sentence INTEGER DEFAULT 0,
                current_time_ms REAL DEFAULT 0,
                is_finished INTEGER DEFAULT 0,
                last_played_at REAL
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_items (
                collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
                item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
                position INTEGER DEFAULT 0,
                PRIMARY KEY (collection_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                site_url TEXT,
                added_at REAL NOT NULL,
                last_fetched REAL
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                sentence_index INTEGER NOT NULL,
                quote TEXT,
                note TEXT,
                created_at REAL NOT NULL
            );
        """)
        for col in ["images TEXT", "reader_html TEXT", "toc TEXT", "audio_requested INTEGER DEFAULT 0"]:
            try:
                db.execute(f"ALTER TABLE items ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS watch_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                added_at REAL NOT NULL,
                last_scanned REAL
            )
        """)


@contextmanager
def get_db():
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        _local.conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_db():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def add_item(
    title,
    source_type,
    text_content,
    sentences,
    source_url=None,
    original_path=None,
    images=None,
    reader_html=None,
    toc=None,
):
    now = time.time()
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO items (title, source_type, source_url, original_path,
               text_content, sentences, images, reader_html, toc, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                source_type,
                source_url,
                original_path,
                text_content,
                json.dumps(sentences),
                json.dumps(images or []),
                reader_html,
                json.dumps(toc) if toc else None,
                now,
                now,
            ),
        )
        item_id = cur.lastrowid
        db.execute("INSERT INTO progress (item_id) VALUES (?)", (item_id,))
    return item_id


def find_duplicate(source_url=None, original_path=None):
    if not source_url and not original_path:
        return None
    with get_db() as db:
        if source_url:
            row = db.execute("SELECT id, title FROM items WHERE source_url = ? LIMIT 1", (source_url,)).fetchone()
            if row:
                return dict(row)
        if original_path:
            row = db.execute("SELECT id, title FROM items WHERE original_path = ? LIMIT 1", (original_path,)).fetchone()
            if row:
                return dict(row)
    return None


def update_item_audio(item_id, timeline, total_duration_ms):
    with get_db() as db:
        db.execute(
            """UPDATE items SET timeline = ?, total_duration_ms = ?,
               audio_ready = 1, updated_at = ? WHERE id = ?""",
            (json.dumps(timeline), total_duration_ms, time.time(), item_id),
        )


def _hydrate_row(row):
    item = dict(row)
    item["sentences"] = json.loads(item["sentences"])
    item["timeline"] = json.loads(item["timeline"]) if item["timeline"] else None
    item["images"] = json.loads(item["images"]) if item.get("images") else []
    item["toc"] = json.loads(item["toc"]) if item.get("toc") else None
    item["progress"] = (
        {
            "current_sentence": row["p_current_sentence"],
            "current_time_ms": row["p_current_time_ms"],
            "is_finished": row["p_is_finished"],
            "last_played_at": row["p_last_played_at"],
        }
        if row["p_current_sentence"] is not None
        else None
    )
    return item


def _hydrate_summary(row):
    item = dict(row)
    item["sentences"] = json.loads(item["sentences"])
    item["progress"] = (
        {
            "current_sentence": row["p_current_sentence"],
            "current_time_ms": row["p_current_time_ms"],
            "is_finished": row["p_is_finished"],
            "last_played_at": row["p_last_played_at"],
        }
        if row["p_current_sentence"] is not None
        else None
    )
    return item


_ITEMS_WITH_PROGRESS = """
    SELECT i.*,
           p.current_sentence AS p_current_sentence,
           p.current_time_ms AS p_current_time_ms,
           p.is_finished AS p_is_finished,
           p.last_played_at AS p_last_played_at
    FROM items i
    LEFT JOIN progress p ON p.item_id = i.id
"""

_ITEMS_SUMMARY = """
    SELECT i.id, i.title, i.source_type, i.source_url, i.sentences,
           i.total_duration_ms, i.audio_ready, i.audio_requested, i.created_at,
           p.current_sentence AS p_current_sentence,
           p.current_time_ms AS p_current_time_ms,
           p.is_finished AS p_is_finished,
           p.last_played_at AS p_last_played_at
    FROM items i
    LEFT JOIN progress p ON p.item_id = i.id
"""


def get_item(item_id):
    with get_db() as db:
        row = db.execute(f"{_ITEMS_WITH_PROGRESS} WHERE i.id = ?", (item_id,)).fetchone()
        if not row:
            return None
        return _hydrate_row(row)


def get_items(source_type=None, collection_id=None):
    with get_db() as db:
        if collection_id:
            rows = db.execute(
                f"""{_ITEMS_SUMMARY}
                    JOIN collection_items ci ON ci.item_id = i.id
                    WHERE ci.collection_id = ?
                    ORDER BY ci.position""",
                (collection_id,),
            ).fetchall()
        elif source_type:
            rows = db.execute(
                f"{_ITEMS_SUMMARY} WHERE i.source_type = ? ORDER BY i.created_at DESC", (source_type,)
            ).fetchall()
        else:
            rows = db.execute(f"{_ITEMS_SUMMARY} ORDER BY i.created_at DESC").fetchall()
        return [_hydrate_summary(r) for r in rows]


def get_in_progress():
    with get_db() as db:
        rows = db.execute(
            f"""{_ITEMS_SUMMARY}
                WHERE p.current_sentence > 0 AND p.is_finished = 0
                ORDER BY p.last_played_at DESC"""
        ).fetchall()
        return [_hydrate_summary(r) for r in rows]


def get_recent(limit=20):
    with get_db() as db:
        rows = db.execute(f"{_ITEMS_SUMMARY} ORDER BY i.created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_hydrate_summary(r) for r in rows]


def search_items(query):
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with get_db() as db:
        rows = db.execute(
            f"{_ITEMS_SUMMARY} WHERE i.title LIKE ? ESCAPE '\\' ORDER BY i.created_at DESC", (f"%{escaped}%",)
        ).fetchall()
        return [_hydrate_summary(r) for r in rows]


def update_progress(item_id, current_sentence, current_time_ms, is_finished=False):
    with get_db() as db:
        db.execute(
            """INSERT INTO progress (item_id, current_sentence, current_time_ms, is_finished, last_played_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(item_id) DO UPDATE SET
               current_sentence = ?, current_time_ms = ?, is_finished = ?, last_played_at = ?""",
            (
                item_id,
                current_sentence,
                current_time_ms,
                int(is_finished),
                time.time(),
                current_sentence,
                current_time_ms,
                int(is_finished),
                time.time(),
            ),
        )


def set_audio_requested(item_id, requested):
    with get_db() as db:
        db.execute("UPDATE items SET audio_requested = ? WHERE id = ?", (int(requested), item_id))


def delete_item(item_id):
    for d in [item_audio_dir(item_id), item_images_dir(item_id)]:
        if os.path.isdir(d):
            for f in os.listdir(d):
                os.unlink(os.path.join(d, f))
            os.rmdir(d)
    with get_db() as db:
        db.execute("DELETE FROM items WHERE id = ?", (item_id,))


def create_collection(name):
    with get_db() as db:
        cur = db.execute("INSERT INTO collections (name, created_at) VALUES (?, ?)", (name, time.time()))
        return cur.lastrowid


def get_collections():
    with get_db() as db:
        rows = db.execute("SELECT * FROM collections ORDER BY name").fetchall()
        result = []
        for row in rows:
            c = dict(row)
            c["count"] = db.execute(
                "SELECT COUNT(*) FROM collection_items WHERE collection_id = ?", (c["id"],)
            ).fetchone()[0]
            result.append(c)
        return result


def add_to_collection(collection_id, item_id):
    with get_db() as db:
        pos = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM collection_items WHERE collection_id = ?", (collection_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, item_id, position) VALUES (?, ?, ?)",
            (collection_id, item_id, pos),
        )


def remove_from_collection(collection_id, item_id):
    with get_db() as db:
        db.execute("DELETE FROM collection_items WHERE collection_id = ? AND item_id = ?", (collection_id, item_id))


def delete_collection(collection_id):
    with get_db() as db:
        db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))


# --- Feed subscriptions ---


def add_feed(title, feed_url, site_url=None):
    now = time.time()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO feeds (title, feed_url, site_url, added_at) VALUES (?, ?, ?, ?)",
            (title, feed_url, site_url, now),
        )
        return cur.lastrowid


def get_feeds():
    with get_db() as db:
        rows = db.execute(
            "SELECT id, title, feed_url, site_url, added_at, last_fetched FROM feeds ORDER BY title COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def find_feed(feed_url):
    with get_db() as db:
        row = db.execute("SELECT id, title FROM feeds WHERE feed_url = ?", (feed_url,)).fetchone()
        return dict(row) if row else None


def delete_feed(feed_id):
    with get_db() as db:
        db.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))


# --- Bookmarks & annotations (a bookmark with a note is an annotation) ---


def add_bookmark(item_id, sentence_index, quote=None, note=None):
    now = time.time()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO bookmarks (item_id, sentence_index, quote, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (item_id, sentence_index, quote, note, now),
        )
        return cur.lastrowid


def get_bookmarks(item_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, item_id, sentence_index, quote, note, created_at "
            "FROM bookmarks WHERE item_id = ? ORDER BY sentence_index, created_at",
            (item_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_bookmark_note(bookmark_id, note):
    with get_db() as db:
        db.execute("UPDATE bookmarks SET note = ? WHERE id = ?", (note, bookmark_id))


def delete_bookmark(bookmark_id):
    with get_db() as db:
        db.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))


# --- Watch folders ---


def add_watch_folder(path):
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO watch_folders (path, added_at) VALUES (?, ?)",
            (path, time.time()),
        )
        return cur.lastrowid


def remove_watch_folder(folder_id):
    with get_db() as db:
        db.execute("DELETE FROM watch_folders WHERE id = ?", (folder_id,))


def get_watch_folders():
    with get_db() as db:
        rows = db.execute("SELECT * FROM watch_folders ORDER BY added_at").fetchall()
        return [dict(r) for r in rows]


def update_watch_folder_scanned(folder_id):
    with get_db() as db:
        db.execute("UPDATE watch_folders SET last_scanned = ? WHERE id = ?", (time.time(), folder_id))


DEFAULTS = {
    "design": "ink",  # single source of truth — templated into index.html + served via /api/settings
    "tts_engine": "edge",
    "edge_voice": "en-US-AriaNeural",
    "say_voice": "Samantha",  # Download Siri voices from System Settings > Accessibility > Spoken Content
    "kokoro_voice": "af_heart",
    "kokoro_model": "kokoro-v1.0-int8",
    "kokoro-mlx_voice": "af_heart",
    "piper_voice": "en_US-lessac-medium",
    "pdf_tables": "off",
}


def get_setting(key):
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else DEFAULTS.get(key)


def set_setting(key, value):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )


def get_all_settings():
    result = dict(DEFAULTS)
    with get_db() as db:
        rows = db.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            result[row[0]] = row[1]
    return result


def item_audio_dir(item_id):
    return os.path.join(AUDIO_DIR, str(item_id))


def item_master_wav(item_id):
    return os.path.join(item_audio_dir(item_id), "master.wav")


def item_master_m4a(item_id):
    return os.path.join(item_audio_dir(item_id), "master.m4a")


def item_images_dir(item_id):
    return os.path.join(IMAGES_DIR, str(item_id))
