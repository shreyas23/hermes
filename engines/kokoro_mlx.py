import os
import threading
import wave

from engines import register
from engines.base import TTSEngine, wav_duration_ms

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


class KokoroMLXEngine(TTSEngine):
    name = "kokoro-mlx"
    max_workers = 2

    def __init__(self):
        self._tts = None
        self._lock = threading.Lock()

    def _get_instance(self):
        with self._lock:
            if self._tts is None:
                from kokoro_mlx import KokoroTTS

                self._tts = KokoroTTS.from_pretrained()
            return self._tts

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        if cancel_event.is_set():
            return i, 0
        import numpy as np

        wav_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        try:
            tts = self._get_instance()
            result = tts.generate(text, voice=voice, speed=speed)
            int16 = (result.audio * 32767).astype(np.int16)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(result.sample_rate)
                wf.writeframes(int16.tobytes())
            return i, wav_duration_ms(wav_path)
        except Exception as e:
            print(f"Failed to generate sentence {i} (kokoro-mlx): {e}")
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            return i, 0

    def list_voices(self):
        return [_voice_meta(v) for v in _VOICE_IDS]


register(KokoroMLXEngine())
