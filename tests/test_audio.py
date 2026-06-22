import os
import wave

from audio import _cleanup_partial, _concatenate_wavs


def _write_wav(path, nframes, framerate=22050):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * nframes)


def _wav_duration_ms(path):
    with wave.open(path, "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def test_wav_duration_helper_one_second(tmp_path):
    path = str(tmp_path / "one.wav")
    _write_wav(path, 22050)
    assert _wav_duration_ms(path) == 1000


def test_wav_duration_helper_half_second(tmp_path):
    path = str(tmp_path / "half.wav")
    _write_wav(path, 11025)
    assert _wav_duration_ms(path) == 500


def test_concatenate_wavs_sums_durations(tmp_path):
    audio_dir = str(tmp_path)
    _write_wav(os.path.join(audio_dir, "sent_0000.wav"), 22050)
    _write_wav(os.path.join(audio_dir, "sent_0001.wav"), 11025)
    output_path = str(tmp_path / "master.wav")

    _concatenate_wavs(audio_dir, 2, output_path)

    assert os.path.isfile(output_path)
    assert _wav_duration_ms(output_path) == 1500


def test_concatenate_wavs_fills_silence_for_missing_files(tmp_path):
    audio_dir = str(tmp_path)
    _write_wav(os.path.join(audio_dir, "sent_0000.wav"), 22050)
    output_path = str(tmp_path / "master.wav")

    _concatenate_wavs(audio_dir, 2, output_path)

    assert os.path.isfile(output_path)
    assert _wav_duration_ms(output_path) == 1100


def test_cleanup_partial_removes_sentence_and_master_files(tmp_path):
    audio_dir = str(tmp_path / "partial")
    os.makedirs(audio_dir)
    sent0 = os.path.join(audio_dir, "sent_0000.wav")
    sent1 = os.path.join(audio_dir, "sent_0001.wav")
    master = os.path.join(audio_dir, "master.wav")
    _write_wav(sent0, 100)
    _write_wav(sent1, 100)
    _write_wav(master, 100)

    _cleanup_partial(audio_dir, 2)

    assert not os.path.exists(sent0)
    assert not os.path.exists(sent1)
    assert not os.path.exists(master)
    assert not os.path.exists(audio_dir)
