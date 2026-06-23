from unittest.mock import MagicMock, patch

from youtube import (
    _clean_cue_text,
    captions_to_sentences,
    extract_video_id,
    is_youtube_url,
    parse_vtt,
)


class TestIsYouTubeUrl:
    def test_watch_url(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_watch_url_extra_params(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s")

    def test_short_url(self):
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")

    def test_shorts_url(self):
        assert is_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")

    def test_embed_url(self):
        assert is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_v_url(self):
        assert is_youtube_url("https://www.youtube.com/v/dQw4w9WgXcQ")

    def test_mobile_url(self):
        assert is_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_http(self):
        assert is_youtube_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_no_www(self):
        assert is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ")

    def test_not_youtube(self):
        assert not is_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")

    def test_channel_page(self):
        assert not is_youtube_url("https://www.youtube.com/c/SomeChannel")

    def test_empty(self):
        assert not is_youtube_url("")

    def test_random_text(self):
        assert not is_youtube_url("not a url at all")

    def test_playlist_only(self):
        assert not is_youtube_url("https://www.youtube.com/playlist?list=PLxxx")


class TestExtractVideoId:
    def test_watch(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts(self):
        assert extract_video_id("https://youtube.com/shorts/abc123DEF_-") == "abc123DEF_-"

    def test_embed(self):
        assert extract_video_id("https://youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid(self):
        assert extract_video_id("https://example.com") is None


class TestCleanCueText:
    def test_strips_c_tags(self):
        assert _clean_cue_text("hello <c>world</c>") == "hello world"

    def test_strips_timing_tags(self):
        assert _clean_cue_text("hello<00:01:23.456> world") == "hello world"

    def test_strips_html(self):
        assert _clean_cue_text("<b>bold</b> and <i>italic</i>") == "bold and italic"

    def test_normalizes_whitespace(self):
        assert _clean_cue_text("hello   \n  world") == "hello world"

    def test_decodes_html_entities(self):
        assert _clean_cue_text("1 &gt; 0 and &amp; &lt; 2") == "1 > 0 and & < 2"

    def test_decodes_apostrophe(self):
        assert _clean_cue_text("it&#39;s fine") == "it's fine"


class TestParseVtt:
    def test_basic(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello world.

00:00:04.000 --> 00:00:07.000
This is a test.
"""
        segments = parse_vtt(vtt)
        assert len(segments) == 2
        assert segments[0] == {"text": "Hello world.", "start_ms": 1000, "end_ms": 4000}
        assert segments[1] == {"text": "This is a test.", "start_ms": 4000, "end_ms": 7000}

    def test_deduplication(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello world.

00:00:02.000 --> 00:00:04.000
Hello world.

00:00:04.000 --> 00:00:06.000
New text.
"""
        segments = parse_vtt(vtt)
        assert len(segments) == 2
        assert segments[0]["text"] == "Hello world."
        assert segments[1]["text"] == "New text."

    def test_sliding_window_dedup(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello world.

00:00:02.000 --> 00:00:05.000
Hello world.
This is new.

00:00:04.000 --> 00:00:07.000
This is new.
Another line.
"""
        segments = parse_vtt(vtt)
        assert len(segments) == 3
        assert segments[0]["text"] == "Hello world."
        assert segments[1]["text"] == "This is new."
        assert segments[2]["text"] == "Another line."

    def test_c_tags_stripped(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
hello <c>world</c>
"""
        segments = parse_vtt(vtt)
        assert segments[0]["text"] == "hello world"

    def test_empty_cues_skipped(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000


00:00:04.000 --> 00:00:07.000
Actual text.
"""
        segments = parse_vtt(vtt)
        assert len(segments) == 1
        assert segments[0]["text"] == "Actual text."

    def test_numbered_cues(self):
        vtt = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
First line.

2
00:00:04.000 --> 00:00:07.000
Second line.
"""
        segments = parse_vtt(vtt)
        assert len(segments) == 2

    def test_short_timestamp(self):
        vtt = """WEBVTT

0:01.000 --> 0:04.000
Short format.
"""
        segments = parse_vtt(vtt)
        assert segments[0]["start_ms"] == 1000
        assert segments[0]["end_ms"] == 4000


class TestCaptionsToSentences:
    def test_basic(self):
        segments = [
            {"text": "Hello world.", "start_ms": 0, "end_ms": 2000},
            {"text": "This is great.", "start_ms": 2000, "end_ms": 4000},
        ]
        segmenter = MagicMock()
        segmenter.segment.return_value = ["Hello world.", "This is great."]

        sentences, timeline = captions_to_sentences(segments, segmenter)
        assert sentences == ["Hello world.", "This is great."]
        assert len(timeline) == 2
        assert timeline[0]["index"] == 0
        assert timeline[0]["start_ms"] == 0
        assert timeline[1]["index"] == 1
        assert timeline[1]["start_ms"] == 2000

    def test_empty(self):
        sentences, timeline = captions_to_sentences([], MagicMock())
        assert sentences == []
        assert timeline == []

    def test_duration_calculation(self):
        segments = [
            {"text": "First.", "start_ms": 0, "end_ms": 3000},
            {"text": "Second.", "start_ms": 3000, "end_ms": 5000},
        ]
        segmenter = MagicMock()
        segmenter.segment.return_value = ["First.", "Second."]

        _, timeline = captions_to_sentences(segments, segmenter)
        assert timeline[0]["duration_ms"] == 3000
        assert timeline[1]["duration_ms"] == 2000


class TestImportRoute:
    @patch("app._start_youtube_download")
    def test_import_creates_item(self, mock_download, client):
        resp = client.post("/api/import/youtube", json={"url": "https://youtube.com/watch?v=abc123DEF_-"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["item_id"] is not None
        assert data["title"] == "abc123DEF_-"
        mock_download.assert_called_once()

    @patch("app._start_youtube_download")
    def test_duplicate_detection(self, mock_download, client):
        url = "https://youtube.com/watch?v=abc123DEF_-"
        client.post("/api/import/youtube", json={"url": url})
        resp = client.post("/api/import/youtube", json={"url": url})
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "duplicate"

    def test_not_youtube_url(self, client):
        resp = client.post("/api/import/youtube", json={"url": "https://example.com"})
        assert resp.status_code == 400

    def test_no_url(self, client):
        resp = client.post("/api/import/youtube", json={})
        assert resp.status_code == 400
