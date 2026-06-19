import json
import os
import queue
import threading
from pathlib import Path

from flask import Flask, Response, render_template, request, jsonify, send_file
from pysbd import Segmenter

from audio import generate_audio_background, cancel_generation
from extractors import SUPPORTED_EXTENSIONS, extract_text
from models import (
    init_db, add_item, get_item, get_items, get_recent, get_in_progress,
    update_progress, delete_item, item_master_wav,
    create_collection, get_collections, add_to_collection,
    remove_from_collection, delete_collection,
)

app = Flask(__name__)
segmenter = Segmenter(language='en', clean=False)

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


@app.route('/')
def index():
    return render_template('index.html')


# --- Library endpoints ---

@app.route('/api/library', methods=['GET'])
def library_list():
    view = request.args.get('view', 'recent')
    source_type = request.args.get('source_type')
    collection_id = request.args.get('collection_id', type=int)

    if view == 'recent':
        items = get_recent()
    elif view == 'in_progress':
        items = get_in_progress()
    elif view == 'collection' and collection_id:
        items = get_items(collection_id=collection_id)
    elif source_type:
        items = get_items(source_type=source_type)
    else:
        items = get_items()

    return jsonify({'items': [_item_summary(i) for i in items]})


@app.route('/api/library/<int:item_id>', methods=['GET'])
def library_item(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'item': item})


@app.route('/api/library/<int:item_id>', methods=['DELETE'])
def library_delete(item_id):
    cancel_generation(item_id)
    delete_item(item_id)
    return jsonify({'deleted': True})


@app.route('/api/library/<int:item_id>/cancel', methods=['POST'])
def library_cancel(item_id):
    cancelled = cancel_generation(item_id)
    if cancelled:
        delete_item(item_id)
        broadcast_sse('generation_cancelled', {'item_id': item_id})
    return jsonify({'cancelled': cancelled})


@app.route('/api/library/<int:item_id>/progress', methods=['POST'])
def library_progress(item_id):
    data = request.json
    update_progress(
        item_id,
        data.get('current_sentence', 0),
        data.get('current_time_ms', 0),
        data.get('is_finished', False),
    )
    return jsonify({'saved': True})


@app.route('/api/library/<int:item_id>/audio')
def library_audio(item_id):
    wav_path = item_master_wav(item_id)
    if not os.path.isfile(wav_path):
        return jsonify({'error': 'Audio not ready'}), 404
    return send_file(wav_path, mimetype='audio/wav')


# --- Import endpoints ---

@app.route('/api/import/file', methods=['POST'])
def import_file():
    file_path = request.json.get('path', '')
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404

    text = extract_text(file_path)
    if not text or not text.strip():
        return jsonify({'error': 'Could not extract text'}), 400

    title = Path(file_path).stem
    sentences = _split(text)

    item_id = add_item(
        title=title,
        source_type='document',
        text_content=text,
        sentences=sentences,
        original_path=file_path,
    )

    _start_generation(item_id, sentences)
    return jsonify({'item_id': item_id, 'title': title, 'sentence_count': len(sentences)})


@app.route('/api/import/url', methods=['POST'])
def import_url():
    import trafilatura

    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return jsonify({'error': 'Could not download page'}), 400

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text or not text.strip():
        return jsonify({'error': 'Could not extract article text'}), 400

    title = url
    try:
        meta_json = trafilatura.extract(downloaded, output_format='json', include_comments=False)
        if meta_json:
            meta = json.loads(meta_json)
            title = meta.get('title', url) or url
    except (ValueError, TypeError):
        pass

    sentences = _split(text)

    item_id = add_item(
        title=title,
        source_type='article',
        text_content=text,
        sentences=sentences,
        source_url=url,
    )

    _start_generation(item_id, sentences)
    return jsonify({'item_id': item_id, 'title': title, 'sentence_count': len(sentences)})


@app.route('/api/import/text', methods=['POST'])
def import_text():
    title = request.json.get('title', 'Untitled').strip()
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'No text provided'}), 400

    sentences = _split(text)

    item_id = add_item(
        title=title,
        source_type='text',
        text_content=text,
        sentences=sentences,
    )

    _start_generation(item_id, sentences)
    return jsonify({'item_id': item_id, 'title': title, 'sentence_count': len(sentences)})


@app.route('/api/import/folder', methods=['POST'])
def import_folder():
    folder = request.json.get('folder', '')
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return jsonify({'error': 'Not a valid directory'}), 400

    files = []
    for f in sorted(Path(folder).iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append({'name': f.name, 'path': str(f), 'ext': f.suffix.lower()})

    return jsonify({'folder': folder, 'files': files})


# --- Collections ---

@app.route('/api/collections', methods=['GET'])
def list_collections():
    return jsonify({'collections': get_collections()})


@app.route('/api/collections', methods=['POST'])
def new_collection():
    name = request.json.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    cid = create_collection(name)
    return jsonify({'id': cid, 'name': name})


@app.route('/api/collections/<int:cid>', methods=['DELETE'])
def del_collection(cid):
    delete_collection(cid)
    return jsonify({'deleted': True})


@app.route('/api/collections/<int:cid>/items', methods=['POST'])
def collection_add(cid):
    item_id = request.json.get('item_id')
    add_to_collection(cid, item_id)
    return jsonify({'added': True})


@app.route('/api/collections/<int:cid>/items/<int:item_id>', methods=['DELETE'])
def collection_remove(cid, item_id):
    remove_from_collection(cid, item_id)
    return jsonify({'removed': True})


# --- SSE ---

@app.route('/api/events')
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

    return Response(stream(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# --- Helpers ---

def _split(text):
    sentences = segmenter.segment(text)
    return [s.strip() for s in sentences if s.strip()]


def _start_generation(item_id, sentences):
    def on_progress(done, total):
        broadcast_sse('generation_progress', {
            'item_id': item_id, 'done': done, 'total': total,
        })

    def on_complete(iid, timeline, total_ms):
        broadcast_sse('generation_complete', {
            'item_id': iid, 'total_duration_ms': total_ms,
        })

    def on_cancel(iid):
        broadcast_sse('generation_cancelled', {'item_id': iid})

    generate_audio_background(item_id, sentences, on_progress, on_complete, on_cancel)


def _item_summary(item):
    return {
        'id': item['id'],
        'title': item['title'],
        'source_type': item['source_type'],
        'source_url': item.get('source_url'),
        'audio_ready': bool(item['audio_ready']),
        'total_duration_ms': item['total_duration_ms'],
        'sentence_count': len(item['sentences']),
        'created_at': item['created_at'],
        'progress': item.get('progress'),
    }


def start_server():
    init_db()
    app.run(port=5123, threaded=True, use_reloader=False)


if __name__ == '__main__':
    import webview
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    webview.create_window(
        'Hermes',
        'http://127.0.0.1:5123',
        width=1100,
        height=750,
        min_size=(800, 500),
    )
    webview.start()
