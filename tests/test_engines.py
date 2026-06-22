import wave

from engines import ENGINE_REGISTRY, get_engine
from engines.base import wav_duration_ms
from engines.kokoro import KokoroEngine


def test_all_engines_registered():
    assert {"say", "edge", "kokoro"} <= set(ENGINE_REGISTRY)


def test_get_engine_returns_named_instance():
    assert get_engine("kokoro").name == "kokoro"
    assert get_engine("edge").name == "edge"
    assert get_engine("say").name == "say"


def test_wav_duration_ms(tmp_path):
    path = str(tmp_path / "one.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)
    assert wav_duration_ms(path) == 1000


def test_say_voices_format():
    voices = get_engine("say").list_voices()
    assert isinstance(voices, list)
    if voices:
        v = voices[0]
        assert {"id", "name", "locale"} <= set(v)


def test_kokoro_voices_hardcoded_list():
    voices = KokoroEngine().list_voices()
    ids = {v["id"] for v in voices}
    assert "af_heart" in ids
    assert "bm_george" in ids
    assert len(voices) == 28
    for v in voices:
        assert {"id", "name", "gender", "locale"} <= set(v)
        assert v["gender"] in ("Female", "Male")
        assert v["locale"] in ("en-US", "en-GB")


def test_kokoro_voice_meta_parsing():
    voices = {v["id"]: v for v in KokoroEngine().list_voices()}
    assert voices["af_heart"] == {"id": "af_heart", "name": "Heart", "gender": "Female", "locale": "en-US"}
    assert voices["bm_george"] == {"id": "bm_george", "name": "George", "gender": "Male", "locale": "en-GB"}
