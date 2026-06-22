import asyncio
import os
import subprocess

from engines import register
from engines.base import TTSEngine, wav_duration_ms


class EdgeEngine(TTSEngine):
    name = "edge"
    max_workers = 8

    def __init__(self):
        self._voices_cache = None

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        if cancel_event.is_set():
            return i, 0
        import edge_tts

        mp3_path = os.path.join(audio_dir, f"sent_{i:04d}.mp3")
        wav_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        try:
            asyncio.run(edge_tts.Communicate(text, voice).save(mp3_path))
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", mp3_path, wav_path],
                check=True,
                capture_output=True,
                timeout=30,
            )
            os.unlink(mp3_path)
            return i, wav_duration_ms(wav_path)
        except Exception as e:
            print(f"Failed to generate sentence {i} (edge): {e}")
            for p in (mp3_path, wav_path):
                if os.path.exists(p):
                    os.unlink(p)
            return i, 0

    def list_voices(self):
        if self._voices_cache is None:
            import edge_tts

            all_voices = asyncio.run(edge_tts.list_voices())
            self._voices_cache = [
                {"id": v["ShortName"], "name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
                for v in all_voices
                if v["Locale"].startswith("en-")
            ]
        return self._voices_cache


register(EdgeEngine())
