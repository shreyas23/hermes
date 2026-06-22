import os
import threading
import urllib.request
import wave

from engines import register
from engines.base import TTSEngine, wav_duration_ms
from models import LIBRARY_DIR

KOKORO_DIR = os.path.join(LIBRARY_DIR, "models", "kokoro")
_RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_VOICES_FILE = "voices-v1.0.bin"

# Maps the kokoro_model setting to the ONNX file published on the kokoro-onnx GitHub release.
_MODEL_FILES = {
    "kokoro-v1.0": "kokoro-v1.0.onnx",
    "kokoro-v1.0-int8": "kokoro-v1.0.int8.onnx",
}

# Derived from the official kokoro VOICES.md (English voices only).
_VOICE_IDS = [
    "af_heart",
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
]


def _voice_meta(voice_id):
    gender_code, _, raw_name = voice_id.partition("_")
    locale = "en-US" if gender_code[0] == "a" else "en-GB"
    gender = "Female" if gender_code[1] == "f" else "Male"
    return {"id": voice_id, "name": raw_name.capitalize(), "gender": gender, "locale": locale}


class KokoroEngine(TTSEngine):
    name = "kokoro"
    max_workers = 3

    def __init__(self):
        self._instance = None
        self._instance_model = None
        self._model = "kokoro-v1.0-int8"
        self._lock = threading.Lock()

    def configure(self, model=None):
        if model:
            self._model = model

    def _ensure_files(self, model_file):
        os.makedirs(KOKORO_DIR, exist_ok=True)
        for fname in (model_file, _VOICES_FILE):
            path = os.path.join(KOKORO_DIR, fname)
            if not os.path.exists(path):
                tmp = path + ".part"
                urllib.request.urlretrieve(_RELEASE_BASE + fname, tmp)
                os.replace(tmp, path)
        return os.path.join(KOKORO_DIR, model_file), os.path.join(KOKORO_DIR, _VOICES_FILE)

    def _get_instance(self):
        model_file = _MODEL_FILES.get(self._model, _MODEL_FILES["kokoro-v1.0-int8"])
        with self._lock:
            if self._instance is None or self._instance_model != model_file:
                from kokoro_onnx import Kokoro

                model_path, voices_path = self._ensure_files(model_file)
                self._instance = Kokoro(model_path, voices_path)
                self._instance_model = model_file
            return self._instance

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        if cancel_event.is_set():
            return i, 0
        import numpy as np

        wav_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        try:
            kokoro = self._get_instance()
            samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
            int16 = (samples * 32767).astype(np.int16)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(int16.tobytes())
            return i, wav_duration_ms(wav_path)
        except Exception as e:
            print(f"Failed to generate sentence {i} (kokoro): {e}")
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            return i, 0

    def list_voices(self):
        return [_voice_meta(v) for v in _VOICE_IDS]


register(KokoroEngine())
