import json
import os
import sqlite3
import time
from contextlib import contextmanager

LIBRARY_DIR = os.path.expanduser('~/sayfiles-library')
DB_PATH = os.path.join(LIBRARY_DIR, 'library.db')
AUDIO_DIR = os.path.join(LIBRARY_DIR, 'audio')


def init_db():
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    with get_db() as db:
        db.executescript('''
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
        ''')


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_item(title, source_type, text_content, sentences, source_url=None, original_path=None):
    now = time.time()
    with get_db() as db:
        cur = db.execute(
            '''INSERT INTO items (title, source_type, source_url, original_path,
               text_content, sentences, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, source_type, source_url, original_path,
             text_content, json.dumps(sentences), now, now)
        )
        item_id = cur.lastrowid
        db.execute('INSERT INTO progress (item_id) VALUES (?)', (item_id,))
    return item_id


def update_item_audio(item_id, timeline, total_duration_ms):
    with get_db() as db:
        db.execute(
            '''UPDATE items SET timeline = ?, total_duration_ms = ?,
               audio_ready = 1, updated_at = ? WHERE id = ?''',
            (json.dumps(timeline), total_duration_ms, time.time(), item_id)
        )


def _hydrate_row(row):
    item = dict(row)
    item['sentences'] = json.loads(item['sentences'])
    item['timeline'] = json.loads(item['timeline']) if item['timeline'] else None
    item['progress'] = {
        'current_sentence': row['p_current_sentence'],
        'current_time_ms': row['p_current_time_ms'],
        'is_finished': row['p_is_finished'],
        'last_played_at': row['p_last_played_at'],
    } if row['p_current_sentence'] is not None else None
    return item


_ITEMS_WITH_PROGRESS = '''
    SELECT i.*,
           p.current_sentence AS p_current_sentence,
           p.current_time_ms AS p_current_time_ms,
           p.is_finished AS p_is_finished,
           p.last_played_at AS p_last_played_at
    FROM items i
    LEFT JOIN progress p ON p.item_id = i.id
'''


def get_item(item_id):
    with get_db() as db:
        row = db.execute(f'{_ITEMS_WITH_PROGRESS} WHERE i.id = ?', (item_id,)).fetchone()
        if not row:
            return None
        return _hydrate_row(row)


def get_items(source_type=None, collection_id=None):
    with get_db() as db:
        if collection_id:
            rows = db.execute(
                f'''{_ITEMS_WITH_PROGRESS}
                    JOIN collection_items ci ON ci.item_id = i.id
                    WHERE ci.collection_id = ?
                    ORDER BY ci.position''',
                (collection_id,)
            ).fetchall()
        elif source_type:
            rows = db.execute(
                f'{_ITEMS_WITH_PROGRESS} WHERE i.source_type = ? ORDER BY i.created_at DESC',
                (source_type,)
            ).fetchall()
        else:
            rows = db.execute(f'{_ITEMS_WITH_PROGRESS} ORDER BY i.created_at DESC').fetchall()
        return [_hydrate_row(r) for r in rows]


def get_in_progress():
    with get_db() as db:
        rows = db.execute(
            f'''{_ITEMS_WITH_PROGRESS}
                WHERE p.current_sentence > 0 AND p.is_finished = 0
                ORDER BY p.last_played_at DESC'''
        ).fetchall()
        return [_hydrate_row(r) for r in rows]


def get_recent(limit=20):
    with get_db() as db:
        rows = db.execute(
            f'{_ITEMS_WITH_PROGRESS} ORDER BY i.created_at DESC LIMIT ?', (limit,)
        ).fetchall()
        return [_hydrate_row(r) for r in rows]


def update_progress(item_id, current_sentence, current_time_ms, is_finished=False):
    with get_db() as db:
        db.execute(
            '''INSERT INTO progress (item_id, current_sentence, current_time_ms, is_finished, last_played_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(item_id) DO UPDATE SET
               current_sentence = ?, current_time_ms = ?, is_finished = ?, last_played_at = ?''',
            (item_id, current_sentence, current_time_ms, int(is_finished), time.time(),
             current_sentence, current_time_ms, int(is_finished), time.time())
        )


def delete_item(item_id):
    audio_dir = item_audio_dir(item_id)
    if os.path.isdir(audio_dir):
        for f in os.listdir(audio_dir):
            os.unlink(os.path.join(audio_dir, f))
        os.rmdir(audio_dir)
    with get_db() as db:
        db.execute('DELETE FROM items WHERE id = ?', (item_id,))


def create_collection(name):
    with get_db() as db:
        cur = db.execute('INSERT INTO collections (name, created_at) VALUES (?, ?)', (name, time.time()))
        return cur.lastrowid


def get_collections():
    with get_db() as db:
        rows = db.execute('SELECT * FROM collections ORDER BY name').fetchall()
        result = []
        for row in rows:
            c = dict(row)
            c['count'] = db.execute(
                'SELECT COUNT(*) FROM collection_items WHERE collection_id = ?', (c['id'],)
            ).fetchone()[0]
            result.append(c)
        return result


def add_to_collection(collection_id, item_id):
    with get_db() as db:
        pos = db.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 FROM collection_items WHERE collection_id = ?',
            (collection_id,)
        ).fetchone()[0]
        db.execute(
            'INSERT OR IGNORE INTO collection_items (collection_id, item_id, position) VALUES (?, ?, ?)',
            (collection_id, item_id, pos)
        )


def remove_from_collection(collection_id, item_id):
    with get_db() as db:
        db.execute(
            'DELETE FROM collection_items WHERE collection_id = ? AND item_id = ?',
            (collection_id, item_id)
        )


def delete_collection(collection_id):
    with get_db() as db:
        db.execute('DELETE FROM collections WHERE id = ?', (collection_id,))


def item_audio_dir(item_id):
    return os.path.join(AUDIO_DIR, str(item_id))


def item_master_wav(item_id):
    return os.path.join(item_audio_dir(item_id), 'master.wav')
