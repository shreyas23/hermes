import asyncio
import os
import subprocess
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from models import item_audio_dir, item_master_wav, item_master_m4a, update_item_audio, delete_item

TTS_WORKERS = 4
EDGE_TTS_VOICE = 'en-US-AriaNeural'


@dataclass
class SentenceTimestamp:
    index: int
    start_ms: float
    duration_ms: float


_active_jobs: dict[int, threading.Event] = {}
_jobs_lock = threading.Lock()


def _generate_sentence_wav_say(i, text, audio_dir, cancel_event):
    if cancel_event.is_set():
        return i, 0
    sent_wav = os.path.join(audio_dir, f'sent_{i:04d}.wav')
    try:
        subprocess.run(
            ['say', '-o', sent_wav, '--file-format=WAVE', '--data-format=LEI16@22050', text],
            check=True, capture_output=True, timeout=60,
        )
        return i, _wav_duration_ms(sent_wav)
    except Exception as e:
        print(f"Failed to generate sentence {i}: {e}")
        return i, 0


async def _generate_sentence_wav_edge(i, text, audio_dir, cancel_event):
    if cancel_event.is_set():
        return i, 0
    import edge_tts
    mp3_path = os.path.join(audio_dir, f'sent_{i:04d}.mp3')
    wav_path = os.path.join(audio_dir, f'sent_{i:04d}.wav')
    try:
        comm = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        await comm.save(mp3_path)
        subprocess.run(
            ['afconvert', '-f', 'WAVE', '-d', 'LEI16@22050', mp3_path, wav_path],
            check=True, capture_output=True, timeout=30,
        )
        os.unlink(mp3_path)
        return i, _wav_duration_ms(wav_path)
    except Exception as e:
        print(f"Failed to generate sentence {i} (edge): {e}")
        for p in (mp3_path, wav_path):
            if os.path.exists(p):
                os.unlink(p)
        return i, 0


def generate_audio_for_item(item_id, sentences, cancel_event, on_progress=None, engine='edge'):
    audio_dir = item_audio_dir(item_id)
    os.makedirs(audio_dir, exist_ok=True)

    durations = [0.0] * len(sentences)
    completed = 0
    progress_lock = threading.Lock()

    if engine == 'edge':
        async def run_edge():
            nonlocal completed
            sem = asyncio.Semaphore(8)
            async def gen(i, text):
                nonlocal completed
                async with sem:
                    idx, dur = await _generate_sentence_wav_edge(i, text, audio_dir, cancel_event)
                    durations[idx] = dur
                    completed += 1
                    if on_progress:
                        on_progress(completed, len(sentences))
            await asyncio.gather(*[gen(i, t) for i, t in enumerate(sentences)])
        asyncio.run(run_edge())
    else:
        with ThreadPoolExecutor(max_workers=TTS_WORKERS) as pool:
            futures = {
                pool.submit(_generate_sentence_wav_say, i, text, audio_dir, cancel_event): i
                for i, text in enumerate(sentences)
            }
            for future in as_completed(futures):
                if cancel_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    _cleanup_partial(audio_dir, len(sentences))
                    return None, 0
                idx, dur = future.result()
                durations[idx] = dur
                with progress_lock:
                    completed += 1
                    if on_progress:
                        on_progress(completed, len(sentences))

    if cancel_event.is_set():
        _cleanup_partial(audio_dir, len(sentences))
        return None, 0

    wav_path = item_master_wav(item_id)
    _concatenate_wavs(audio_dir, len(sentences), wav_path)

    m4a_path = item_master_m4a(item_id)
    _convert_to_m4a(wav_path, m4a_path)
    os.unlink(wav_path)

    timestamps = []
    cumulative_ms = 0
    for i, dur in enumerate(durations):
        timestamps.append(SentenceTimestamp(index=i, start_ms=cumulative_ms, duration_ms=dur))
        cumulative_ms += dur

    for i in range(len(sentences)):
        sent_wav = os.path.join(audio_dir, f'sent_{i:04d}.wav')
        if os.path.exists(sent_wav):
            os.unlink(sent_wav)

    timeline = [{'index': t.index, 'start_ms': t.start_ms, 'duration_ms': t.duration_ms} for t in timestamps]
    update_item_audio(item_id, timeline, cumulative_ms)

    return timeline, cumulative_ms


def generate_audio_background(item_id, sentences, on_progress=None, on_complete=None, on_cancel=None, engine='edge'):
    cancel_event = threading.Event()

    with _jobs_lock:
        if item_id in _active_jobs:
            _active_jobs[item_id].set()
        _active_jobs[item_id] = cancel_event

    def run():
        try:
            timeline, total_ms = generate_audio_for_item(item_id, sentences, cancel_event, on_progress, engine)
            if timeline is None:
                if on_cancel:
                    on_cancel(item_id)
            elif on_complete:
                on_complete(item_id, timeline, total_ms)
        finally:
            with _jobs_lock:
                if _active_jobs.get(item_id) is cancel_event:
                    del _active_jobs[item_id]

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def cancel_generation(item_id):
    with _jobs_lock:
        event = _active_jobs.get(item_id)
        if event:
            event.set()
            return True
    return False


def is_generating(item_id):
    with _jobs_lock:
        return item_id in _active_jobs


def _cleanup_partial(audio_dir, count):
    for i in range(count):
        path = os.path.join(audio_dir, f'sent_{i:04d}.wav')
        if os.path.exists(path):
            os.unlink(path)
    for name in ('master.wav', 'master.m4a'):
        path = os.path.join(audio_dir, name)
        if os.path.exists(path):
            os.unlink(path)
    try:
        os.rmdir(audio_dir)
    except OSError:
        pass


def _convert_to_m4a(wav_path, m4a_path):
    subprocess.run(
        ['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '64000', wav_path, m4a_path],
        check=True, capture_output=True, timeout=300,
    )


def _concatenate_wavs(audio_dir, count, output_path):
    with wave.open(output_path, 'wb') as out:
        for i in range(count):
            sent_path = os.path.join(audio_dir, f'sent_{i:04d}.wav')
            if not os.path.exists(sent_path):
                continue
            with wave.open(sent_path, 'rb') as inp:
                if i == 0:
                    out.setparams(inp.getparams())
                out.writeframes(inp.readframes(inp.getnframes()))


def _wav_duration_ms(path):
    with wave.open(path, 'rb') as wf:
        return (wf.getnframes() / wf.getframerate()) * 1000
