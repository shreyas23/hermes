import time

from discovery import _normalize_entry, strip_html


def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_none_returns_empty():
    assert strip_html(None) == ""


def test_strip_html_empty_returns_empty():
    assert strip_html("") == ""


def test_normalize_entry_has_expected_keys():
    entry = {
        "title": "Gravity explained",
        "link": "https://example.com/gravity",
        "summary": "A short summary about gravity.",
        "published": "Mon, 22 Jun 2026 10:00:00 GMT",
        "published_parsed": time.struct_time((2026, 6, 22, 10, 0, 0, 0, 173, 0)),
    }

    result = _normalize_entry(entry, "Science Feed")

    assert set(result.keys()) == {"title", "url", "summary", "published", "feed_title", "ts"}
    assert result["title"] == "Gravity explained"
    assert result["url"] == "https://example.com/gravity"
    assert result["summary"] == "A short summary about gravity."
    assert result["feed_title"] == "Science Feed"
    assert result["ts"] > 0


def test_normalize_entry_missing_published_parsed_does_not_crash():
    entry = {
        "title": "No date here",
        "link": "https://example.com/nodate",
        "summary": "Summary without a parsed date.",
    }

    result = _normalize_entry(entry, "Feed")

    assert result["ts"] == 0
    assert result["title"] == "No date here"


def test_normalize_entry_strips_html_from_title():
    entry = {
        "title": "<b>Bold</b> headline",
        "link": "https://example.com/bold",
        "summary": "",
    }

    result = _normalize_entry(entry, "Feed")

    assert result["title"] == "Bold headline"
