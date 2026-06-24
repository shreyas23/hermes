# Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

import os
import subprocess
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from engines import get_engine
from models import close_db, item_audio_dir, item_master_m4a, item_master_wav, update_item_audio


@dataclass
class SentenceTimestamp:
    index: int
    start_ms: float
    duration_ms: float


_active_jobs: dict[int, threading.Event] = {}
_jobs_lock = threading.Lock()


def generate_audio_for_item(item_id, sentences, cancel_event, on_progress=None, engine="edge", voice=None, model=None):
    audio_dir = item_audio_dir(item_id)
    os.makedirs(audio_dir, exist_ok=True)

    tts = get_engine(engine)
    tts.configure(model=model)

    durations = [0.0] * len(sentences)
    completed = 0
    progress_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=tts.max_workers) as pool:
        futures = {
            pool.submit(tts.generate_sentence, i, text, audio_dir, cancel_event, voice): i
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

    if not os.path.isfile(wav_path):
        return None, 0

    m4a_path = item_master_m4a(item_id)
    try:
        _convert_to_m4a(wav_path, m4a_path)
        if os.path.isfile(m4a_path) and os.path.getsize(m4a_path) > 0:
            os.unlink(wav_path)
    except Exception as e:
        print(f"M4A conversion failed, keeping WAV: {e}")

    timestamps = []
    cumulative_ms = 0
    for i, dur in enumerate(durations):
        timestamps.append(SentenceTimestamp(index=i, start_ms=cumulative_ms, duration_ms=dur))
        cumulative_ms += dur

    for i in range(len(sentences)):
        sent_wav = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        if os.path.exists(sent_wav):
            os.unlink(sent_wav)

    timeline = [{"index": t.index, "start_ms": t.start_ms, "duration_ms": t.duration_ms} for t in timestamps]
    update_item_audio(item_id, timeline, cumulative_ms, tts_engine=engine)

    return timeline, cumulative_ms


def generate_audio_background(
    item_id, sentences, on_progress=None, on_complete=None, on_cancel=None, engine="edge", voice=None, model=None
):
    cancel_event = threading.Event()

    with _jobs_lock:
        if item_id in _active_jobs:
            _active_jobs[item_id].set()
        _active_jobs[item_id] = cancel_event

    def run():
        try:
            timeline, total_ms = generate_audio_for_item(
                item_id, sentences, cancel_event, on_progress, engine, voice, model
            )
            if timeline is None:
                if on_cancel:
                    on_cancel(item_id)
            elif on_complete:
                on_complete(item_id, timeline, total_ms)
        except Exception as e:
            print(f"Audio generation failed for item {item_id}: {e}")
            if on_cancel:
                on_cancel(item_id)
        finally:
            with _jobs_lock:
                if _active_jobs.get(item_id) is cancel_event:
                    del _active_jobs[item_id]
            close_db()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def cancel_generation(item_id, wait=False):
    with _jobs_lock:
        event = _active_jobs.get(item_id)
        if not event:
            return False
        event.set()
    if wait:
        for _ in range(100):
            import time

            time.sleep(0.1)
            with _jobs_lock:
                if item_id not in _active_jobs:
                    break
    return True


def is_generating(item_id):
    with _jobs_lock:
        return item_id in _active_jobs


def _cleanup_partial(audio_dir, count):
    for i in range(count):
        for ext in (".wav", ".mp3"):
            path = os.path.join(audio_dir, f"sent_{i:04d}{ext}")
            if os.path.exists(path):
                os.unlink(path)
    for name in ("master.wav", "master.m4a"):
        path = os.path.join(audio_dir, name)
        if os.path.exists(path):
            os.unlink(path)
    try:
        os.rmdir(audio_dir)
    except OSError:
        pass


def _convert_to_m4a(wav_path, m4a_path):
    from models import get_setting

    raw = get_setting("audio_bitrate") or "64000"
    bitrate = raw if raw.isdigit() else "64000"
    subprocess.run(
        ["afconvert", "-f", "m4af", "-d", "aac", "-b", bitrate, wav_path, m4a_path],
        check=True,
        capture_output=True,
        timeout=300,
    )


def _concatenate_wavs(audio_dir, count, output_path):
    from models import get_setting

    try:
        pause_ms = int(get_setting("sentence_pause_ms") or 100)
    except (TypeError, ValueError):
        pause_ms = 100
    params_set = False
    framerate = 22050
    with wave.open(output_path, "wb") as out:
        for i in range(count):
            sent_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
            if not os.path.exists(sent_path):
                if params_set and pause_ms > 0:
                    silence_frames = int(framerate * 2 * pause_ms / 1000)
                    out.writeframes(b"\x00" * silence_frames)
                continue
            with wave.open(sent_path, "rb") as inp:
                if not params_set:
                    out.setparams(inp.getparams())
                    framerate = inp.getframerate()
                    params_set = True
                out.writeframes(inp.readframes(inp.getnframes()))
    if not params_set:
        os.unlink(output_path)
