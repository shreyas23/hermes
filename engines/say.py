import os
import subprocess

from engines import register
from engines.base import TTSEngine, wav_duration_ms


class SayEngine(TTSEngine):
    name = "say"
    max_workers = 4

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        if cancel_event.is_set():
            return i, 0
        wav_path = os.path.join(audio_dir, f"sent_{i:04d}.wav")
        try:
            subprocess.run(
                ["say", "-v", voice, "-o", wav_path, "--file-format=WAVE", "--data-format=LEI16@22050", text],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return i, wav_duration_ms(wav_path)
        except Exception as e:
            print(f"Failed to generate sentence {i} (say): {e}")
            return i, 0

    def list_voices(self):
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        voices = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "en_" in line:
                name = parts[0]
                voices.append({"id": name, "name": name, "locale": parts[1]})
        return voices


register(SayEngine())
