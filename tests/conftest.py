import os
import wave

import pytest

import models


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Every test gets a fresh SQLite database in a temp directory."""
    models.LIBRARY_DIR = str(tmp_path)
    models.DB_PATH = str(tmp_path / "test.db")
    models.AUDIO_DIR = str(tmp_path / "audio")
    models.IMAGES_DIR = str(tmp_path / "images")
    models.init_db()
    yield tmp_path
    models.close_db()


@pytest.fixture
def client():
    """Flask test client with isolated DB already initialized."""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def sample_item():
    """Insert a basic text item and return (item_id, sentences)."""
    sentences = ["First sentence about gravity.", "Second sentence about momentum.", "Third sentence about energy."]
    item_id = models.add_item(
        title="Test Item",
        source_type="text",
        text_content=" ".join(sentences),
        sentences=sentences,
    )
    return item_id, sentences


@pytest.fixture
def audio_ready_item(sample_item):
    """Item with a synthetic silent WAV so audio routes work."""
    item_id, sentences = sample_item
    audio_dir = models.item_audio_dir(item_id)
    os.makedirs(audio_dir, exist_ok=True)
    wav_path = models.item_master_wav(item_id)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 22050)
    timeline = [{"index": i, "start_ms": i * 333, "duration_ms": 333} for i in range(len(sentences))]
    models.update_item_audio(item_id, timeline, 1000)
    return item_id, sentences
