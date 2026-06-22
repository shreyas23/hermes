import wave


class TTSEngine:
    name: str
    max_workers: int = 4

    def configure(self, **kwargs):
        pass

    def generate_sentence(self, i, text, audio_dir, cancel_event, voice, speed=1.0):
        raise NotImplementedError

    def list_voices(self):
        return []


def wav_duration_ms(path):
    with wave.open(path, "rb") as wf:
        return (wf.getnframes() / wf.getframerate()) * 1000
