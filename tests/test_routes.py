"""Integration tests for app.py Flask routes using the test client."""


# --- Import: text ---


def test_import_text_ok(client):
    resp = client.post("/api/import/text", json={"title": "Test", "text": "Hello world."})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "item_id" in data
    assert data["title"] == "Test"


def test_import_text_empty_is_400(client):
    resp = client.post("/api/import/text", json={"title": "Test", "text": "   "})
    assert resp.status_code == 400


def test_import_text_missing_is_400(client):
    resp = client.post("/api/import/text", json={"title": "Test"})
    assert resp.status_code == 400


# --- Import: file (404 + duplicate 409) ---


def test_import_file_nonexistent_is_404(client):
    resp = client.post("/api/import/file", json={"path": "/no/such/file.txt"})
    assert resp.status_code == 404


def test_import_file_duplicate_is_409(client, isolated_db):
    f = isolated_db / "doc.txt"
    f.write_text("Some words here. More words follow.")
    first = client.post("/api/import/file", json={"path": str(f)})
    assert first.status_code == 200
    second = client.post("/api/import/file", json={"path": str(f)})
    assert second.status_code == 409
    assert second.get_json()["error"] == "duplicate"


# --- Import: url ---


def test_import_url_missing_is_400(client):
    resp = client.post("/api/import/url", json={})
    assert resp.status_code == 400


def test_import_url_blocks_private_ip(client):
    resp = client.post("/api/import/url", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert resp.status_code == 400
    assert "blocked" in resp.get_json()["error"].lower()


# --- Import: folder (lists files, does not import) ---


def test_import_folder_lists_txt_files(client, isolated_db):
    (isolated_db / "a.txt").write_text("alpha")
    (isolated_db / "b.txt").write_text("beta")
    resp = client.post("/api/import/folder", json={"folder": str(isolated_db)})
    assert resp.status_code == 200
    files = resp.get_json()["files"]
    names = {f["name"] for f in files}
    assert {"a.txt", "b.txt"} <= names
    for f in files:
        assert "path" in f and "ext" in f


# --- Library: get / delete / search ---


def test_get_item_nonexistent_is_404(client):
    resp = client.get("/api/library/999999")
    assert resp.status_code == 404


def test_get_item_ok(client, sample_item):
    item_id, sentences = sample_item
    resp = client.get(f"/api/library/{item_id}")
    assert resp.status_code == 200
    item = resp.get_json()["item"]
    assert item["title"] == "Test Item"
    assert item["sentences"] == sentences


def test_delete_item(client, sample_item):
    item_id, _ = sample_item
    resp = client.delete(f"/api/library/{item_id}")
    assert resp.status_code == 200
    assert client.get(f"/api/library/{item_id}").status_code == 404


def test_search_matches(client, sample_item):
    # search_items matches on title, not body text
    resp = client.get("/api/library/search?q=Test")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert any(i["title"] == "Test Item" for i in items)


# --- Progress ---


def test_progress_save_and_persist(client, sample_item):
    item_id, _ = sample_item
    resp = client.post(
        f"/api/library/{item_id}/progress",
        json={"current_sentence": 2, "current_time_ms": 5000},
    )
    assert resp.status_code == 200

    item = client.get(f"/api/library/{item_id}").get_json()["item"]
    assert item["progress"]["current_sentence"] == 2


# --- Bookmarks ---


def test_bookmark_missing_index_is_400(client, sample_item):
    item_id, _ = sample_item
    resp = client.post(f"/api/library/{item_id}/bookmarks", json={"note": "hi"})
    assert resp.status_code == 400


def test_bookmark_lifecycle(client, sample_item):
    item_id, _ = sample_item
    create = client.post(
        f"/api/library/{item_id}/bookmarks",
        json={"sentence_index": 1, "quote": "Second sentence about momentum.", "note": "first"},
    )
    assert create.status_code == 200
    bid = create.get_json()["id"]

    patch = client.patch(f"/api/bookmarks/{bid}", json={"note": "updated"})
    assert patch.status_code == 200

    bookmarks = client.get(f"/api/library/{item_id}/bookmarks").get_json()["bookmarks"]
    assert any(b["id"] == bid and b["note"] == "updated" for b in bookmarks)

    delete = client.delete(f"/api/bookmarks/{bid}")
    assert delete.status_code == 200

    bookmarks = client.get(f"/api/library/{item_id}/bookmarks").get_json()["bookmarks"]
    assert all(b["id"] != bid for b in bookmarks)


# --- Audio ---


def test_audio_ready_returns_audio(client, audio_ready_item):
    item_id, _ = audio_ready_item
    resp = client.get(f"/api/library/{item_id}/audio")
    assert resp.status_code == 200
    assert "audio" in resp.headers["Content-Type"]


def test_audio_missing_is_404(client, sample_item):
    item_id, _ = sample_item
    resp = client.get(f"/api/library/{item_id}/audio")
    assert resp.status_code == 404


# --- Security: path traversal ---


def test_image_path_traversal_is_403(client, sample_item):
    item_id, _ = sample_item
    resp = client.get(f"/api/library/{item_id}/images/../../etc/passwd")
    assert resp.status_code == 403


# --- Settings ---


def test_settings_update_and_persist(client):
    resp = client.post("/api/settings", json={"design": "glass"})
    assert resp.status_code == 200
    assert client.get("/api/settings").get_json()["design"] == "glass"


def test_settings_unknown_key_ignored(client):
    resp = client.post("/api/settings", json={"fake_key": "value"})
    assert resp.status_code == 200
    assert "fake_key" not in client.get("/api/settings").get_json()
