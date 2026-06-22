import os

import models

# --- Item CRUD ---


def test_add_item_returns_int_id_and_creates_progress_row(sample_item):
    item_id, _ = sample_item
    assert isinstance(item_id, int)
    item = models.get_item(item_id)
    assert item is not None
    assert item["progress"] is not None
    assert item["progress"]["current_sentence"] == 0


def test_get_item_returns_none_for_nonexistent_id():
    assert models.get_item(99999) is None


def test_json_fields_round_trip_through_hydrate_row():
    sentences = ["one.", "two."]
    images = [{"src": "a.png", "after": 0}]
    toc = [{"level": 1, "title": "Intro", "id": "intro"}]
    item_id = models.add_item(
        title="JSON Item",
        source_type="pdf",
        text_content="one. two.",
        sentences=sentences,
        images=images,
        toc=toc,
    )
    models.update_item_audio(item_id, [{"index": 0, "start_ms": 0, "duration_ms": 10}], 10)

    item = models.get_item(item_id)
    assert item["sentences"] == sentences
    assert isinstance(item["sentences"], list)
    assert item["images"] == images
    assert isinstance(item["images"], list)
    assert item["toc"] == toc
    assert isinstance(item["toc"], list)
    assert isinstance(item["timeline"], list)
    assert item["timeline"][0]["start_ms"] == 0


def test_get_items_ordered_by_created_at_desc():
    first = models.add_item("First", "text", "a.", ["a."])
    second = models.add_item("Second", "text", "b.", ["b."])
    items = models.get_items()
    ids = [i["id"] for i in items]
    assert ids.index(second) < ids.index(first)


def test_get_items_filters_by_source_type():
    text_id = models.add_item("Text", "text", "a.", ["a."])
    models.add_item("PDF", "pdf", "b.", ["b."])
    items = models.get_items(source_type="text")
    assert [i["id"] for i in items] == [text_id]


def test_get_items_filters_by_collection_id(sample_item):
    item_id, _ = sample_item
    other_id = models.add_item("Other", "text", "x.", ["x."])
    coll_id = models.create_collection("C")
    models.add_to_collection(coll_id, item_id)
    items = models.get_items(collection_id=coll_id)
    ids = [i["id"] for i in items]
    assert item_id in ids
    assert other_id not in ids


def test_delete_item_removes_db_row(sample_item):
    item_id, _ = sample_item
    models.delete_item(item_id)
    assert models.get_item(item_id) is None


def test_delete_item_cascades_to_progress(sample_item):
    item_id, _ = sample_item
    models.update_progress(item_id, 1, 100)
    models.delete_item(item_id)
    with models.get_db() as db:
        row = db.execute("SELECT 1 FROM progress WHERE item_id = ?", (item_id,)).fetchone()
    assert row is None


def test_delete_item_cascades_to_bookmarks(sample_item):
    item_id, _ = sample_item
    models.add_bookmark(item_id, 1, quote="q")
    models.delete_item(item_id)
    assert models.get_bookmarks(item_id) == []


def test_delete_item_cascades_to_collection_items(sample_item):
    item_id, _ = sample_item
    coll_id = models.create_collection("C")
    models.add_to_collection(coll_id, item_id)
    models.delete_item(item_id)
    with models.get_db() as db:
        row = db.execute("SELECT 1 FROM collection_items WHERE item_id = ?", (item_id,)).fetchone()
    assert row is None


def test_delete_item_cleans_up_disk_dirs(sample_item):
    item_id, _ = sample_item
    audio_dir = models.item_audio_dir(item_id)
    images_dir = models.item_images_dir(item_id)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    with open(os.path.join(audio_dir, "master.wav"), "wb") as f:
        f.write(b"x")
    with open(os.path.join(images_dir, "img.png"), "wb") as f:
        f.write(b"x")
    models.delete_item(item_id)
    assert not os.path.isdir(audio_dir)
    assert not os.path.isdir(images_dir)


# --- Duplicate detection ---


def test_find_duplicate_matches_source_url():
    item_id = models.add_item("U", "url", "a.", ["a."], source_url="http://example.com")
    dup = models.find_duplicate(source_url="http://example.com")
    assert dup is not None
    assert dup["id"] == item_id


def test_find_duplicate_matches_original_path():
    item_id = models.add_item("F", "pdf", "a.", ["a."], original_path="/tmp/test.pdf")
    dup = models.find_duplicate(original_path="/tmp/test.pdf")
    assert dup is not None
    assert dup["id"] == item_id


def test_find_duplicate_returns_none_when_no_match():
    models.add_item("U", "url", "a.", ["a."], source_url="http://example.com")
    assert models.find_duplicate(source_url="http://nomatch.com") is None


# --- Progress ---


def test_update_progress_upserts_second_wins(sample_item):
    item_id, _ = sample_item
    models.update_progress(item_id, 1, 100)
    models.update_progress(item_id, 2, 200)
    progress = models.get_item(item_id)["progress"]
    assert progress["current_sentence"] == 2
    assert progress["current_time_ms"] == 200


def test_update_progress_marks_finished(sample_item):
    item_id, _ = sample_item
    models.update_progress(item_id, 3, 1000, is_finished=True)
    assert models.get_item(item_id)["progress"]["is_finished"] == 1


def test_get_in_progress_excludes_finished_and_unstarted(sample_item):
    item_id, _ = sample_item
    started = models.add_item("Started", "text", "a.", ["a."])
    finished = models.add_item("Finished", "text", "b.", ["b."])
    models.update_progress(started, 1, 50)
    models.update_progress(finished, 2, 200, is_finished=True)
    ids = [i["id"] for i in models.get_in_progress()]
    assert started in ids
    assert finished not in ids
    assert item_id not in ids  # current_sentence still 0


def test_get_recent_respects_limit():
    for n in range(4):
        models.add_item(f"Item {n}", "text", "a.", ["a."])
    assert len(models.get_recent(limit=2)) == 2


# --- Search ---


def test_search_items_matches_title():
    item_id = models.add_item("Notes on gravity", "text", "x.", ["x."])
    results = models.search_items("gravity")
    assert item_id in [r["id"] for r in results]


def test_search_items_escapes_percent_wildcard():
    models.add_item("Plain title", "text", "x.", ["x."])
    # A literal "%" must not behave as a wildcard matching everything.
    assert models.search_items("%") == []


# --- Collections ---


def test_create_and_add_to_collection_visible_via_get_items(sample_item):
    item_id, _ = sample_item
    coll_id = models.create_collection("My Collection")
    models.add_to_collection(coll_id, item_id)
    assert [i["id"] for i in models.get_items(collection_id=coll_id)] == [item_id]


def test_add_to_collection_auto_increments_position(sample_item):
    item_id, _ = sample_item
    other_id = models.add_item("Other", "text", "x.", ["x."])
    coll_id = models.create_collection("C")
    models.add_to_collection(coll_id, item_id)
    models.add_to_collection(coll_id, other_id)
    with models.get_db() as db:
        rows = db.execute(
            "SELECT item_id, position FROM collection_items WHERE collection_id = ? ORDER BY position",
            (coll_id,),
        ).fetchall()
    assert [(r["item_id"], r["position"]) for r in rows] == [(item_id, 0), (other_id, 1)]


def test_remove_from_collection(sample_item):
    item_id, _ = sample_item
    coll_id = models.create_collection("C")
    models.add_to_collection(coll_id, item_id)
    models.remove_from_collection(coll_id, item_id)
    assert models.get_items(collection_id=coll_id) == []


def test_delete_collection_cascades_membership_but_keeps_items(sample_item):
    item_id, _ = sample_item
    coll_id = models.create_collection("C")
    models.add_to_collection(coll_id, item_id)
    models.delete_collection(coll_id)
    assert models.get_item(item_id) is not None
    with models.get_db() as db:
        row = db.execute("SELECT 1 FROM collection_items WHERE collection_id = ?", (coll_id,)).fetchone()
    assert row is None


# --- Feeds ---


def test_add_feed_and_get_feeds():
    feed_id = models.add_feed("Test Feed", "http://example.com/feed.xml")
    feeds = models.get_feeds()
    assert any(f["id"] == feed_id and f["title"] == "Test Feed" for f in feeds)


def test_find_feed_match_and_no_match():
    models.add_feed("Test Feed", "http://example.com/feed.xml")
    assert models.find_feed("http://example.com/feed.xml") is not None
    assert models.find_feed("http://other.com") is None


def test_delete_feed():
    feed_id = models.add_feed("Test Feed", "http://example.com/feed.xml")
    models.delete_feed(feed_id)
    assert models.get_feeds() == []


# --- Bookmarks ---


def test_add_and_get_bookmark(sample_item):
    item_id, _ = sample_item
    bm_id = models.add_bookmark(item_id, 1, quote="test")
    bookmarks = models.get_bookmarks(item_id)
    assert len(bookmarks) == 1
    assert bookmarks[0]["id"] == bm_id
    assert bookmarks[0]["quote"] == "test"


def test_update_bookmark_note_persists(sample_item):
    item_id, _ = sample_item
    bm_id = models.add_bookmark(item_id, 1, quote="test")
    models.update_bookmark_note(bm_id, "my note")
    assert models.get_bookmarks(item_id)[0]["note"] == "my note"


def test_delete_bookmark(sample_item):
    item_id, _ = sample_item
    bm_id = models.add_bookmark(item_id, 1, quote="test")
    models.delete_bookmark(bm_id)
    assert models.get_bookmarks(item_id) == []
