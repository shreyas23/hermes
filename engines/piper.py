import os
import threading
import wave
from pathlib import Path

from engines import register
from engines.base import TTSEngine, wav_duration_ms
from models import LIBRARY_DIR

PIPER_DIR = Path(LIBRARY_DIR) / "models" / "piper"

_DEFAULT_VOICES = [
    "en_US-lessac-medium",
    "en_US-lessac-high",
    "en_US-amy-medium",
    "en_US-danny-low",
    "en_US-joe-medium",
    "en_US-john-medium",
    "en_US-kathleen-low",
    "en_US-kristin-medium",
    "en_US-kusal-medium",
    "en_US-ryan-medium",
    "en_US-ryan-high",
    "en_GB-alan-medium",
    "en_GB-alba-medium",
    "en_GB-aru-medium",
    "en_GB-jenny_dioco-medium",
    "en_GB-northern_english_male-medium",
    "en_GB-semaine-medium",
    "en_GB-southern_english_female-low",
    "en_GB-vctk-medium",
]


def _voice_meta(voice_id):
    parts = voice_id.split("-")
    locale = parts[0].replace("_", "-")
    name = parts[1].replace("_", " ").title()
    quality = parts[2] if len(parts) > 2 else "medium"
    return {"id": voice_id, "name": f"{name} ({quality})", "locale": locale}


class PiperEngine(TTSEngine):
    name = "piper"
    max_workers = 4

    def __init__(self):
        self._voices = {}
        self._lock = threading.Lock()

    def _ensure_voice(self, voice_id):
        with self._lock:
            if voice_id in self._voices:
                return self._voices[voice_id]

            from piper import PiperVoice
            from piper.download_voices import download_voice

            model_path = PIPER_DIR / f"{voice_id}.onnx"
            if not model_path.exists():
                PIPER_DIR.mkdir(parents=True, exist_ok=True)
                download_voice(voice_id, PIPER_DIR)

            voice = PiperVoice.load(str(model_path))
            self._voices[voice_id] = voice
            return voice

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        if cancel_event.is_set():
            return i, 0

        wav_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        try:
            piper_voice = self._ensure_voice(voice)
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(length_scale=1.0 / speed if speed else 1.0)
            with wave.open(wav_path, "wb") as wf:
                piper_voice.synthesize_wav(text, wf, syn_config=syn_config)
            return i, wav_duration_ms(wav_path)
        except Exception as e:
            print(f"Failed to generate sentence {i} (piper): {e}")
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            return i, 0

    def list_voices(self):
        return [_voice_meta(v) for v in _DEFAULT_VOICES]


register(PiperEngine())
