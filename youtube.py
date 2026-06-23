import glob
import os
import re
import tempfile

import yt_dlp

_YOUTUBE_URL_RE = re.compile(
    r"""^https?://
        (?:(?:www|m)\.)?
        (?:
            youtube\.com/(?:watch\?(?:[^\s]*&)?v=|shorts/|embed/|v/)([A-Za-z0-9_-]{11})
            |
            youtu\.be/([A-Za-z0-9_-]{11})
        )
        (?:[?&#/].*)?$
    """,
    re.VERBOSE,
)


def is_youtube_url(url):
    return bool(_YOUTUBE_URL_RE.match(url.strip()))


def extract_video_id(url):
    match = _YOUTUBE_URL_RE.match(url.strip())
    if not match:
        return None
    return match.group(1) or match.group(2)


def fetch_metadata(url):
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", ""),
        "duration_s": float(info.get("duration") or 0),
        "channel": info.get("channel") or info.get("uploader") or "",
        "video_id": info.get("id", ""),
    }


def download_audio(url, output_dir, cancel_event, on_progress=None):
    def progress_hook(d):
        if cancel_event.is_set():
            raise _CancelledError()
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")
            if total and downloaded:
                on_progress(downloaded / total * 100)

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(output_dir, "master.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError:
        return None
    except _CancelledError:
        return None

    m4a_path = os.path.join(output_dir, "master.m4a")
    return m4a_path if os.path.isfile(m4a_path) else None


def fetch_captions(url):
    with tempfile.TemporaryDirectory() as tmp:
        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "vtt",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(tmp, "%(id)s"),
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError:
            return None

        vtt_files = glob.glob(os.path.join(tmp, "*.vtt"))
        if not vtt_files:
            return None

        manual = [f for f in vtt_files if ".auto." not in os.path.basename(f)]
        chosen = _pick_caption_file(manual or vtt_files)
        if not chosen:
            return None

        with open(chosen, encoding="utf-8") as f:
            return f.read()


def _pick_caption_file(files):
    for lang in ("en", "en-US", "en-GB"):
        for f in files:
            if f".{lang}." in os.path.basename(f):
                return f
    return files[0] if files else None


def parse_vtt(vtt_content):
    blocks = re.split(r"\n\s*\n", vtt_content.strip())
    raw_cues = []

    for block in blocks:
        lines = block.strip().splitlines()
        timing_idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_idx is None:
            continue

        start_ms, end_ms = _parse_timing_line(lines[timing_idx])
        if start_ms is None:
            continue

        cue_lines = [_clean_cue_text(line) for line in lines[timing_idx + 1 :]]
        cue_lines = [line for line in cue_lines if line]
        if not cue_lines:
            continue

        raw_cues.append({"lines": cue_lines, "start_ms": start_ms, "end_ms": end_ms})

    # YouTube auto-captions use a sliding window: each cue shows 2 lines,
    # overlapping with neighbors. Deduplicate by tracking which lines we've seen.
    segments = []
    seen_lines = set()

    for cue in raw_cues:
        new_lines = [line for line in cue["lines"] if line not in seen_lines]
        if not new_lines:
            continue

        for line in cue["lines"]:
            seen_lines.add(line)

        text = " ".join(new_lines)
        segments.append({"text": text, "start_ms": cue["start_ms"], "end_ms": cue["end_ms"]})

    return segments


_TS = r"\d{1,2}:\d{2}:\d{2}\.\d{3}|\d{1,2}:\d{2}\.\d{3}"
_TIMING_RE = re.compile(rf"({_TS})\s*-->\s*({_TS})")


def _parse_timing_line(line):
    match = _TIMING_RE.search(line)
    if not match:
        return None, None
    return _timestamp_to_ms(match.group(1)), _timestamp_to_ms(match.group(2))


def _timestamp_to_ms(ts):
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, rest = parts
    else:
        h = "0"
        m, rest = parts
    s, ms = rest.split(".")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def _clean_cue_text(text):
    import html

    text = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", text)
    text = re.sub(r"</?c[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def captions_to_sentences(segments, segmenter):
    if not segments:
        return [], []

    full_text = ""
    offsets = []
    for seg in segments:
        offsets.append((len(full_text), seg["start_ms"]))
        full_text += seg["text"] + " "
    full_text = full_text.rstrip()

    final_end_ms = segments[-1]["end_ms"]

    sentences = [s.strip() for s in segmenter.segment(full_text) if s.strip()]

    starts = []
    search_pos = 0
    for sentence in sentences:
        idx = full_text.find(sentence, search_pos)
        if idx == -1:
            idx = search_pos
        search_pos = idx + len(sentence)
        starts.append(_start_ms_for_offset(idx, offsets))

    timeline = []
    for i, start_ms in enumerate(starts):
        if i + 1 < len(starts):
            duration_ms = starts[i + 1] - start_ms
        else:
            duration_ms = final_end_ms - start_ms
        timeline.append({"index": i, "start_ms": float(start_ms), "duration_ms": float(max(duration_ms, 0))})

    return sentences, timeline


def _start_ms_for_offset(offset, offsets):
    result = offsets[0][1]
    for char_offset, start_ms in offsets:
        if char_offset <= offset:
            result = start_ms
        else:
            break
    return result


class _CancelledError(Exception):
    pass
