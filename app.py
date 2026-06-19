import json
import os
import queue
import threading
import time
from pathlib import Path

from flask import Flask, Response, render_template, request, jsonify, send_file
from pysbd import Segmenter

from audio import generate_audio_background, cancel_generation, is_generating
from extractors import SUPPORTED_EXTENSIONS, extract_with_images, extract_url_with_images, map_images_to_sentences, clean_html_for_reader
from models import (
    init_db, add_item, get_item, get_items, get_recent, get_in_progress,
    search_items, update_progress, delete_item, item_master_wav, item_master_m4a,
    item_images_dir, create_collection, get_collections, add_to_collection,
    remove_from_collection, delete_collection,
    get_all_settings, get_setting, set_setting,
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


@app.route('/api/library/search', methods=['GET'])
def library_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'items': []})
    items = search_items(query)
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


@app.route('/api/library/<int:item_id>/retry', methods=['POST'])
def library_retry(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    if item['audio_ready']:
        return jsonify({'error': 'Audio already generated'}), 400
    _start_generation(item_id, item['sentences'])
    return jsonify({'retrying': True, 'item_id': item_id})


@app.route('/api/library/<int:item_id>/images/<path:filename>')
def library_image(item_id, filename):
    img_dir = item_images_dir(item_id)
    filepath = os.path.join(img_dir, filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': 'Image not found'}), 404
    return send_file(filepath)


@app.route('/api/library/<int:item_id>/audio')
def library_audio(item_id):
    m4a_path = item_master_m4a(item_id)
    if os.path.isfile(m4a_path):
        return send_file(m4a_path, mimetype='audio/mp4')
    wav_path = item_master_wav(item_id)
    if os.path.isfile(wav_path):
        return send_file(wav_path, mimetype='audio/wav')
    return jsonify({'error': 'Audio not ready'}), 404


# --- Import endpoints ---

@app.route('/api/import/file', methods=['POST'])
def import_file():
    file_path = request.json.get('path', '')
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404

    item_id_placeholder = int(time.time() * 1000) % 1000000
    img_dir = item_images_dir(item_id_placeholder)
    os.makedirs(img_dir, exist_ok=True)

    result = extract_with_images(file_path, img_dir)
    if not result or not result['text'].strip():
        return jsonify({'error': 'Could not extract text'}), 400

    text = result['text']
    title = Path(file_path).stem
    sentences = _split(text)
    images = map_images_to_sentences(result.get('images', []), text, sentences)

    item_id = add_item(
        title=title,
        source_type='document',
        text_content=text,
        sentences=sentences,
        original_path=file_path,
        images=images,
    )

    real_img_dir = item_images_dir(item_id)
    if img_dir != real_img_dir:
        if os.path.isdir(img_dir) and os.listdir(img_dir):
            os.makedirs(real_img_dir, exist_ok=True)
            for f in os.listdir(img_dir):
                os.rename(os.path.join(img_dir, f), os.path.join(real_img_dir, f))
        if os.path.isdir(img_dir):
            try:
                os.rmdir(img_dir)
            except OSError:
                pass

    _start_generation(item_id, sentences)
    return jsonify({'item_id': item_id, 'title': title, 'sentence_count': len(sentences)})


@app.route('/api/import/url', methods=['POST'])
def import_url():
    import trafilatura

    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            downloaded = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return jsonify({'error': f'Could not download page: {e}'}), 400
    if not downloaded:
        return jsonify({'error': 'Could not download page'}), 400

    from readability import Document as ReadabilityDoc
    reader_html = clean_html_for_reader(downloaded, url)

    rdoc = ReadabilityDoc(downloaded)
    title = rdoc.title() if rdoc.title() and rdoc.title() != '[no-title]' else None
    if not title:
        from bs4 import BeautifulSoup as BS
        title_tag = BS(downloaded, 'html.parser').find('title')
        title = title_tag.string.strip() if title_tag and title_tag.string else None
    if not title:
        first_h = BeautifulSoup(reader_html, 'html.parser').find(['h1', 'h2', 'h3'])
        title = first_h.get_text().strip() if first_h else url
    if not reader_html or not reader_html.strip():
        return jsonify({'error': 'Could not extract article text'}), 400

    from bs4 import BeautifulSoup
    text_only = BeautifulSoup(reader_html, 'html.parser').get_text(separator='\n', strip=True)
    if not text_only.strip():
        return jsonify({'error': 'Could not extract article text'}), 400

    sentences = _split(text_only)

    item_id = add_item(
        title=title,
        source_type='article',
        text_content=text_only,
        sentences=sentences,
        source_url=url,
        reader_html=reader_html,
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


# --- Settings ---

@app.route('/api/settings', methods=['GET'])
def settings_get():
    return jsonify(get_all_settings())


@app.route('/api/settings', methods=['POST'])
def settings_update():
    data = request.json
    for key, value in data.items():
        set_setting(key, value)
    return jsonify(get_all_settings())


@app.route('/api/voices', methods=['GET'])
def voices_list():
    engine = request.args.get('engine', 'edge')
    if engine == 'edge':
        import asyncio
        import edge_tts
        async def fetch():
            return await edge_tts.list_voices()
        all_voices = asyncio.run(fetch())
        voices = [{'id': v['ShortName'], 'name': v['ShortName'], 'gender': v['Gender'], 'locale': v['Locale']}
                  for v in all_voices if v['Locale'].startswith('en-')]
        return jsonify({'voices': voices})
    else:
        import subprocess
        out = subprocess.run(['say', '-v', '?'], capture_output=True, text=True)
        voices = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and 'en_' in line:
                name = parts[0]
                voices.append({'id': name, 'name': name, 'locale': parts[1] if len(parts) > 1 else ''})
        return jsonify({'voices': voices})


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

    engine = get_setting('tts_engine')
    voice = get_setting('edge_voice') if engine == 'edge' else get_setting('say_voice')
    generate_audio_background(item_id, sentences, on_progress, on_complete, on_cancel, engine=engine, voice=voice)


def _item_summary(item):
    audio_ready = bool(item['audio_ready'])
    generating = not audio_ready and is_generating(item['id'])
    return {
        'id': item['id'],
        'title': item['title'],
        'source_type': item['source_type'],
        'source_url': item.get('source_url'),
        'audio_ready': audio_ready,
        'generating': generating,
        'interrupted': not audio_ready and not generating,
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
