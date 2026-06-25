# Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt", ".rtf", ".html", ".htm"}

_BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div", "td", "th"]


def inject_sentence_spans(html, sentences):
    """Wrap each sentence's text in <span data-si="N"> inside reader HTML.

    Uses two passes: first wraps multi-node sentences (those spanning inline
    elements) at the block-child level, then rebuilds the word index and wraps
    single-node sentences via text-node splitting.
    """
    from collections import defaultdict

    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html, "html.parser")

    def norm(w):
        return re.sub(r"[^\w']", "", w.lower())

    def build_words():
        words = []
        for tn in soup.find_all(string=True):
            for m in re.finditer(r"\S+", str(tn)):
                n = norm(m.group())
                if n:
                    words.append((n, tn, m.start(), m.end()))
        return words

    def match_all(words):
        matches = []
        wi = 0
        for si, sent in enumerate(sentences):
            sw = [norm(w) for w in sent.split() if norm(w)]
            if not sw:
                continue
            plen = min(4, len(sw))
            found = -1
            for i in range(wi, len(words) - plen + 1):
                if all(words[i + j][0] == sw[j] for j in range(plen)):
                    found = i
                    break
            if found == -1:
                continue
            end = found
            for j in range(len(sw)):
                if found + j >= len(words):
                    break
                if words[found + j][0] == sw[j]:
                    end = found + j
                else:
                    break
            matches.append((si, found, end))
            wi = end + 1
        return matches

    # --- Pass 1: wrap multi-node sentences at block-child level ---
    words = build_words()
    matches = match_all(words)
    handled = set()

    # Group multi-node matches by block parent
    multi_by_block = defaultdict(list)
    for si, sw_idx, ew_idx in matches:
        start_node, end_node = words[sw_idx][1], words[ew_idx][1]
        if start_node is not end_node:
            block = start_node.find_parent(_BLOCK_TAGS)
            if block:
                sc = _ancestor_child_of(block, start_node)
                ec = _ancestor_child_of(block, end_node)
                if sc and ec:
                    multi_by_block[id(block)].append((si, block, sc, words[sw_idx][2], ec, words[ew_idx][3]))

    for block_id, group in multi_by_block.items():
        if len(group) == 1:
            # One multi-node sentence in this block — EPUB-style wrap
            si, block, sc, s_off, ec, e_off = group[0]
            if _wrap_sentence_range(soup, si, block, sc, s_off, ec, e_off):
                handled.add(si)
        else:
            # Multiple multi-node sentences share a block — tag block for each
            for si, block, sc, s_off, ec, e_off in group:
                if "data-si" not in block.attrs:
                    block["data-si"] = str(si)
                handled.add(si)

    # --- Pass 2: rebuild word index, wrap single-node sentences ---
    words = build_words()
    matches = match_all(words)

    single = defaultdict(list)
    for si, sw_idx, ew_idx in matches:
        if si in handled:
            continue
        start_node, end_node = words[sw_idx][1], words[ew_idx][1]
        if start_node is end_node:
            single[id(start_node)].append((si, words[sw_idx][2], words[ew_idx][3], start_node))

    for entries in single.values():
        entries.sort(key=lambda x: x[1])
        text_node = entries[0][3]
        text = str(text_node)

        parts = []
        pos = 0
        for si, start_off, end_off, _ in entries:
            if start_off > pos:
                parts.append(NavigableString(text[pos:start_off]))
            span = soup.new_tag("span")
            span["data-si"] = str(si)
            span.string = text[start_off:end_off]
            parts.append(span)
            pos = end_off
        if pos < len(text):
            parts.append(NavigableString(text[pos:]))

        if parts:
            first = parts[0]
            text_node.replace_with(first)
            prev = first
            for part in parts[1:]:
                prev.insert_after(part)
                prev = part

    # Strip data-si from parent elements whose children already have data-si.
    # This prevents nested data-si spans that cause cascading style conflicts.
    for el in list(soup.select("[data-si]")):
        if el.select("[data-si]"):
            del el["data-si"]

    return str(soup)


def _ancestor_child_of(block, node):
    """Walk up from node to find the direct child of block that contains it."""
    current = node
    while current and current.parent is not block:
        current = current.parent
    return current


def _wrap_sentence_range(soup, si, block, sc, s_off, ec, e_off):
    """Wrap a sentence range in a <span data-si> within a block element.
    Returns True on success."""
    from bs4 import NavigableString

    try:
        actual_start = sc
        if isinstance(sc, NavigableString) and s_off > 0:
            text = str(sc)
            before = NavigableString(text[:s_off])
            after = NavigableString(text[s_off:])
            sc.replace_with(before)
            before.insert_after(after)
            actual_start = after

        actual_end = ec
        if isinstance(ec, NavigableString) and e_off < len(str(ec)):
            text = str(ec)
            sent_part = NavigableString(text[:e_off])
            rest_part = NavigableString(text[e_off:])
            ec.replace_with(sent_part)
            sent_part.insert_after(rest_part)
            actual_end = sent_part

        to_wrap = []
        current = actual_start
        while current:
            to_wrap.append(current)
            if current is actual_end:
                break
            current = current.next_sibling
        else:
            return False

        if to_wrap:
            span = soup.new_tag("span")
            span["data-si"] = str(si)
            to_wrap[0].insert_before(span)
            for node in to_wrap:
                span.append(node.extract())
            return True
    except Exception as e:
        print(f"Warning: failed to wrap sentence {si}: {e}")
        return False
    return False


def extract_text(file_path: str) -> str | None:
    result = extract_with_images(file_path)
    return result["text"] if result else None


def extract_with_images(file_path: str, image_dir: str = None) -> dict | None:
    ext = Path(file_path).suffix.lower()
    extractors = {
        ".txt": _extract_txt,
        ".md": _extract_md,
        ".html": _extract_html,
        ".htm": _extract_html,
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".rtf": _extract_rtf,
    }
    fn = extractors.get(ext)
    if not fn:
        return None
    try:
        return fn(file_path, image_dir)
    except Exception as e:
        print(f"Extraction error for {file_path}: {e}")
        return None


_WIKI_CITATION_RE = re.compile(
    r"\[(?:\d+[a-z]?|note\s+\d+|nb\s+\d+|citation needed|edit|update|"
    r"clarification needed|page needed|who\?|when\?|why\?)\]",
    re.IGNORECASE,
)


def _is_wikipedia_url(url: str) -> bool:
    return "wikipedia.org/wiki/" in (url or "")


def _strip_wikipedia_cruft(soup) -> None:
    """Remove Wikipedia citation markers, edit links, and reference/nav blocks
    so they are neither displayed nor read aloud."""
    for sel in (
        "sup.reference",
        "span.mw-editsection",
        "ol.references",
        "div.reflist",
        "div.refbegin",
        "div.navbox",
        "table.navbox",
        "div.mw-references-wrap",
        "div.hatnote",
    ):
        for el in soup.select(sel):
            el.decompose()
    for cls in ("noprint", "mw-cite-backlink", "mw-empty-elt", "reference"):
        for el in soup.find_all(class_=cls):
            el.decompose()


def _strip_citation_text(soup) -> None:
    """Safety net: remove any bracketed citation markers left in plain text."""
    for node in soup.find_all(string=_WIKI_CITATION_RE.search):
        node.replace_with(_WIKI_CITATION_RE.sub("", node))


_HEADING_RE = re.compile(r"^h[1-6]$")


def _strip_empty_paragraphs(soup) -> None:
    """Drop paragraphs with no text or image (e.g. leftover navbox-styles)."""
    for p in soup.find_all("p"):
        if p.find(_HEADING_RE):
            continue  # heading wrapper — not empty
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()


def _heading_wrapper(node):
    """If node is a heading (or a <p> wrapping one), return (wrapper, level)."""
    name = getattr(node, "name", None)
    if not name:
        return None, None
    if _HEADING_RE.match(name):
        parent = node.parent
        if parent is not None and parent.name == "p" and "mw-heading" in (parent.get("class") or []):
            return parent, int(name[1])
        return node, int(name[1])
    if name == "p":
        h = node.find(_HEADING_RE)
        if h:
            return node, int(h.name[1])
    return None, None


_APPENDIX_TITLES = {
    "see also",
    "notes",
    "references",
    "citations",
    "sources",
    "footnotes",
    "explanatory notes",
    "notes and references",
    "general sources",
    "general references",
    "bibliography",
    "works cited",
    "further reading",
    "external links",
}


def _strip_appendix_sections(soup) -> None:
    """Remove standard Wikipedia appendix sections (See also, References, External
    links, etc.) — heading plus its whole span — since they are reference/navigation
    apparatus, not article prose, even when they still contain links."""
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        wrapper, level = _heading_wrapper(heading)
        if wrapper is None or wrapper.parent is None:
            continue
        if heading.get_text(strip=True).lower() not in _APPENDIX_TITLES:
            continue
        to_remove = [wrapper]
        for sib in wrapper.next_siblings:
            _, sib_level = _heading_wrapper(sib)
            if sib_level is not None and sib_level <= level:
                break
            to_remove.append(sib)
        for el in to_remove:
            if hasattr(el, "decompose"):
                el.decompose()
            else:
                el.extract()


def _strip_empty_sections(soup) -> None:
    """Remove headings whose section has no content — the orphaned appendix
    headers (See also, References, etc.) left behind once their reference and
    link lists are stripped. Iterates so empty parents collapse after their
    empty children are removed."""
    changed = True
    while changed:
        changed = False
        for heading in soup.find_all(list("h%d" % i for i in range(1, 7))):
            wrapper, level = _heading_wrapper(heading)
            if wrapper is None or wrapper.parent is None:
                continue
            empty = True
            for sib in wrapper.next_siblings:
                _, sib_level = _heading_wrapper(sib)
                if sib_level is not None:
                    if sib_level <= level:
                        break  # next section at same or higher level
                    continue  # deeper subheading — handled on its own
                name = getattr(sib, "name", None)
                if name is None:
                    # NavigableString (note: it is a str subclass, so guard before .find)
                    if str(sib).strip():
                        empty = False
                        break
                    continue
                if name == "img" or sib.find("img") or sib.get_text(strip=True):
                    empty = False
                    break
            if empty:
                wrapper.decompose()
                changed = True


def clean_html_for_reader(html: str, base_url: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup
    from readability import Document

    is_wikipedia = _is_wikipedia_url(base_url)

    # Pre-process: unwrap <picture> to expose <img>, capture dimensions
    orig_soup = BeautifulSoup(html, "html.parser")
    if is_wikipedia:
        _strip_wikipedia_cruft(orig_soup)
    img_dims = {}
    for img in orig_soup.find_all("img"):
        src = img.get("src", "")
        if src:
            dims = {}
            if img.get("height") and img["height"]:
                dims["height"] = str(img["height"])
            if img.get("width") and img["width"]:
                dims["width"] = str(img["width"])
            if dims:
                img_dims[src] = dims

    for picture in orig_soup.find_all("picture"):
        img = picture.find("img")
        if img:
            picture.replace_with(img)
        else:
            source = picture.find("source")
            if source and source.get("srcset"):
                new_img = orig_soup.new_tag("img", src=source["srcset"].split()[0])
                picture.replace_with(new_img)

    doc = Document(str(orig_soup))
    reader_html = doc.summary()
    raw_title = doc.title()
    doc_title = raw_title if raw_title and raw_title != "[no-title]" else None

    soup = BeautifulSoup(reader_html, "html.parser")
    if is_wikipedia:
        _strip_wikipedia_cruft(soup)
        _strip_citation_text(soup)
        _strip_appendix_sections(soup)
        _strip_empty_paragraphs(soup)
        _strip_empty_sections(soup)

    # Re-add title that readability extracts separately
    if doc_title:
        content = soup.find("div") or soup
        first_child = content.find()
        if first_child:
            h1 = soup.new_tag("h1")
            h1.string = doc_title
            first_child.insert_before(h1)

    for tag in soup.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if v}
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src:
            abs_src = urljoin(base_url, src)
            img["src"] = abs_src
            # Restore original dimensions
            orig = img_dims.get(src) or img_dims.get(abs_src) or {}
            for attr in ("height", "width"):
                if attr in orig and attr not in img.attrs:
                    img[attr] = orig[attr]
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href:
            a["href"] = urljoin(base_url, href)

    # Re-inject content images that readability dropped
    def _img_key(url):
        m = re.search(r"([\w-]{20,}\.\w{3,4})$", url.split("?")[0].split("%2F")[-1])
        return m.group(1) if m else url

    reader_img_keys = {_img_key(img.get("src", "")) for img in soup.find_all("img")}
    text_nodes = list(soup.find_all(string=True))
    article = orig_soup.find("article") or orig_soup.find("main") or orig_soup
    for img in article.find_all("img"):
        src = img.get("src", "")
        abs_src = urljoin(base_url, src) if src else ""
        key = _img_key(abs_src)
        if not abs_src or key in reader_img_keys:
            continue
        w = str(img.get("width", "999")).split(".")[0]
        h = str(img.get("height", "999")).split(".")[0]
        if (w.isdigit() and int(w) < 100) or (h.isdigit() and int(h) < 50):
            continue

        alt = img.get("alt", "")
        prev_text = ""
        for sib in img.previous_siblings:
            t = getattr(sib, "get_text", lambda: str(sib))()
            if t.strip():
                prev_text = t.strip()
                break

        new_img = soup.new_tag("img", src=abs_src)
        if alt:
            new_img["alt"] = alt
        if w.isdigit() and int(w) > 0:
            new_img["width"] = w
        if h.isdigit() and int(h) > 0:
            new_img["height"] = h

        inserted = False
        if prev_text:
            words = prev_text[-40:].split()
            search = " ".join(words[-4:]) if len(words) >= 4 else prev_text[-20:]
            for tn in text_nodes:
                if search in str(tn):
                    parent = tn.find_parent()
                    if parent:
                        parent.insert_after(new_img)
                        inserted = True
                        break

        if not inserted:
            paras = soup.find_all("p")
            if paras:
                ratio = len(reader_img_keys) / max(len(paras), 1)
                insert_at = min(int(ratio * len(paras)), len(paras) - 1)
                paras[insert_at].insert_after(new_img)

        reader_img_keys.add(key)

    title = doc_title
    if not title:
        title_tag = BeautifulSoup(html, "html.parser").find("title")
        title = title_tag.string.strip() if title_tag and title_tag.string else None
    if not title:
        first_h = soup.find(["h1", "h2", "h3"])
        title = first_h.get_text().strip() if first_h else None

    return str(soup), title or ""


def extract_url_with_images(html: str, base_url: str, image_dir: str = None) -> dict | None:

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    body = soup.find("article") or soup.find("main") or soup.find("body") or soup
    blocks = []
    char_offset = 0

    img_count = 0
    for el in body.descendants:
        if el.name == "img":
            src = el.get("src", "")
            if not src or src.startswith("data:"):
                continue
            src = urljoin(base_url, src)
            alt = el.get("alt", "")
            img_entry = {"type": "image", "src": src, "alt": alt, "char_offset": char_offset}
            if image_dir:
                local = _download_image(src, image_dir, img_count)
                if local:
                    img_entry["filename"] = local
            img_count += 1
            blocks.append(img_entry)
        elif el.string and el.parent.name not in ("script", "style", "img"):
            text = el.string.strip()
            if text:
                blocks.append({"type": "text", "content": text, "char_offset": char_offset})
                char_offset += len(text) + 1

    full_text = " ".join(b["content"] for b in blocks if b["type"] == "text")
    total_chars = char_offset or 1
    images = []
    for b in blocks:
        if b["type"] == "image" and b.get("filename"):
            b["total_chars"] = total_chars
            images.append(b)

    return {"text": full_text, "images": images}


def map_images_to_sentences(images: list, text: str, sentences: list) -> list:
    if not images or not sentences:
        return []

    mapped = []
    for img in images:
        char_pos = img.get("char_offset", 0)
        total_chars = img.get("total_chars", 1) or 1
        ratio = char_pos / total_chars
        after_sentence = min(int(ratio * len(sentences)), len(sentences) - 1)
        mapped.append(
            {
                "after_sentence": after_sentence,
                "filename": img.get("filename", ""),
                "alt": img.get("alt", ""),
            }
        )

    return mapped


def _is_safe_url(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    return True


def _check_ip(host, port=None, family=0):
    """Resolve and validate that the IP is not private/internal (SSRF guard)."""
    import ipaddress
    import socket

    results = socket.getaddrinfo(host, port or 443, family, socket.SOCK_STREAM)
    for family, _, _, _, sockaddr in results:
        ip_str = sockaddr[0]
        addr = ipaddress.ip_address(ip_str)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"Blocked internal address: {ip_str}")
    return results


def safe_urlopen(req, **kwargs):
    """urlopen with SSRF protection: validates resolved IPs and checks redirects."""
    if isinstance(req, str):
        req = urllib.request.Request(req)
    host = urllib.parse.urlparse(req.full_url).hostname
    _check_ip(host)
    resp = urllib.request.urlopen(req, **kwargs)
    final_host = urllib.parse.urlparse(resp.url).hostname
    if final_host and final_host != host:
        try:
            _check_ip(final_host)
        except ValueError:
            resp.close()
            raise
    return resp


def _download_image(url: str, image_dir: str, index: int) -> str | None:
    if not _is_safe_url(url):
        return None
    try:
        ext = _guess_image_ext(url)
        filename = f"img_{index}{ext}"
        filepath = os.path.join(image_dir, filename)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with safe_urlopen(req, timeout=10) as resp:
            data = resp.read(5 * 1024 * 1024)
            with open(filepath, "wb") as f:
                f.write(data)
        if os.path.getsize(filepath) < 100:
            os.unlink(filepath)
            return None
        return filename
    except Exception as e:
        print(f"Failed to download image {url}: {e}")
        return None


def _guess_image_ext(url: str) -> str:
    url_lower = url.split("?")[0].lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        if url_lower.endswith(ext):
            return ext
    return ".jpg"


# --- Format extractors (return dict with text + images) ---


def _extract_txt(path: str, image_dir: str = None) -> dict:
    with open(path, "r", errors="ignore") as f:
        return {"text": f.read(), "images": []}


def _extract_md(path: str, image_dir: str = None) -> dict:
    import markdown as md_lib

    with open(path, "r", errors="ignore") as f:
        text = f.read()

    images = []
    if image_dir:
        for i, match in enumerate(re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text)):
            alt, src = match.group(1), match.group(2)
            if src.startswith("http"):
                local = _download_image(src, image_dir, i)
            elif os.path.isfile(os.path.join(os.path.dirname(path), src)):
                import shutil

                ext = Path(src).suffix
                local = f"img_{i}{ext}"
                shutil.copy2(os.path.join(os.path.dirname(path), src), os.path.join(image_dir, local))
            else:
                continue
            if local:
                images.append(
                    {
                        "type": "image",
                        "filename": local,
                        "alt": alt,
                        "char_offset": match.start(),
                        "total_chars": len(text) or 1,
                    }
                )

    # Python-Markdown needs a blank line before lists/blockquotes following a paragraph
    text = re.sub(r"([^\n])\n([-*+] |\d+\. |> )", r"\1\n\n\2", text)

    md = md_lib.Markdown(extensions=["extra", "toc"])
    html = md.convert(text)
    reader_html, toc = _normalize_reader_headings(html)

    return {"text": _html_to_plain_text(reader_html), "images": images, "reader_html": reader_html, "toc": toc}


def _normalize_reader_headings(html):
    """Rewrite heading ids to the h-N convention and return (html, toc)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    toc = []
    counter = 0
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        counter += 1
        hid = f"h-{counter}"
        h["id"] = hid
        title = h.get_text().strip()
        if title:
            toc.append({"level": min(int(h.name[1]), 3), "title": title, "id": hid})
    return str(soup), toc


def _html_to_plain_text(html):
    """Flatten reader HTML into clean plain text for sentence splitting."""
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]):
        tag.insert_before(NavigableString("\n\n"))
    flat = soup.get_text()
    flat = re.sub(r"[ \t]+", " ", flat)
    flat = re.sub(r"\n{3,}", "\n\n", flat)
    # Single newlines are source line-wraps within blocks — collapse to spaces
    flat = re.sub(r"(?<!\n)\n(?!\n)", " ", flat)
    return flat.strip()


def _extract_html(path: str, image_dir: str = None) -> dict:
    with open(path, "r", errors="ignore") as f:
        html = f.read()
    return extract_url_with_images(html, f"file://{path}", image_dir)


def _extract_pdf(path: str, image_dir: str = None) -> dict:
    import pymupdf
    from pymupdf4llm.helpers.pymupdf_rag import TocHeaders
    from pymupdf4llm.helpers.pymupdf_rag import to_markdown as p4l_to_markdown

    with pymupdf.open(path) as doc:
        hdr_info = TocHeaders(doc)
        md = p4l_to_markdown(doc, hdr_info=hdr_info)
        toc_titles = [title for _, title, _ in doc.get_toc()]
        md = _clean_pdf_markdown(md, toc_titles)
        reader_html = _pdf_md_to_html(md)
        toc = _build_pdf_toc(doc, reader_html)

        from bs4 import BeautifulSoup, NavigableString

        soup = BeautifulSoup(reader_html, "html.parser")
        for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]):
            tag.insert_before(NavigableString("\n\n"))
        flat_text = soup.get_text()
        flat_text = re.sub(r"[ \t]+", " ", flat_text)
        flat_text = re.sub(r"\n{3,}", "\n\n", flat_text)
        flat_text = flat_text.strip()

        images = []
        if image_dir:
            char_offset = 0
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                for i, img in enumerate(page.get_images(full=True)):
                    try:
                        xref = img[0]
                        pix = pymupdf.Pixmap(doc, xref)
                        if pix.n > 4:
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                        filename = f"img_p{page_num}_{i}.png"
                        pix.save(os.path.join(image_dir, filename))
                        if os.path.getsize(os.path.join(image_dir, filename)) > 500:
                            images.append(
                                {
                                    "type": "image",
                                    "filename": filename,
                                    "alt": f"Page {page_num + 1} image",
                                    "char_offset": char_offset + len(page_text or "") // 2,
                                }
                            )
                    except Exception:
                        pass
                char_offset += len(page_text or "") + 2
            total_chars = char_offset or 1
            for img in images:
                img["total_chars"] = total_chars

    return {"text": flat_text, "images": images, "reader_html": reader_html, "toc": toc}


def _clean_pdf_markdown(md, toc_titles=None):
    lines = md.split("\n")
    result = []
    skip_toc = False

    toc_set = set()
    if toc_titles:
        for t in toc_titles:
            toc_set.add(re.sub(r"\s+", " ", t.strip().lower()))

    for line in lines:
        stripped = line.strip()

        if re.match(r"^(?:#{1,6}\s+)?\*?\*?Contents\*?\*?\s*$", stripped, re.IGNORECASE):
            skip_toc = True
            continue
        if skip_toc:
            if re.match(r"^#{1,6}\s", stripped):
                skip_toc = False
            elif toc_set and stripped:
                text_clean = re.sub(r"[_*]", "", stripped).strip()
                norm = re.sub(r"\s+", " ", text_clean.lower())
                if norm in toc_set and len(text_clean) < 80:
                    skip_toc = False
                else:
                    continue
            else:
                continue

        if stripped.count("_") >= 6 and re.search(r"\d+$", stripped):
            continue

        if stripped.isdigit() and len(stripped) <= 3:
            continue

        if stripped.startswith("=== "):
            continue

        if toc_set and not re.match(r"^#{1,6}\s", stripped) and stripped:
            text_clean = re.sub(r"[_*]", "", stripped).strip()
            norm = re.sub(r"\s+", " ", text_clean.lower())
            if norm in toc_set and len(text_clean) < 80:
                level = 1
                if re.match(r"^\d+\.\d+\.\d+", text_clean):
                    level = 3
                elif re.match(r"^\d+\.\d+", text_clean):
                    level = 2
                result.append(f"{'#' * level} {stripped}")
                continue

        result.append(line)

    return "\n".join(result)


def _pdf_md_to_html(md):
    import markdown as md_lib
    from bs4 import BeautifulSoup

    cleaned_lines = []
    for line in md.split("\n"):
        m = re.match(r"^(#{1,6})\s+.*?\d+\s+(\*\*\d+[\s.]+.+)", line)
        if m:
            cleaned_lines.append(f"{m.group(1)} {m.group(2)}")
        else:
            cleaned_lines.append(line)
    md = "\n".join(cleaned_lines)

    from models import get_setting

    use_tables = get_setting("pdf_tables") != "off"
    extensions = ["tables"] if use_tables else []
    html = md_lib.markdown(md, extensions=extensions)

    soup = BeautifulSoup(html, "html.parser")
    counter = 0
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        counter += 1
        h["id"] = f"h-{counter}"
        for strong in h.find_all("strong"):
            strong.unwrap()

    _merge_pdf_table_rows(soup)

    return str(soup)


def _merge_pdf_table_rows(soup):
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        for row in rows:
            cells = row.find_all(["th", "td"])
            for i, cell in enumerate(cells):
                t = cell.get_text().strip()
                if re.match(r"^Col\d+$", t):
                    cell.string = ""
                if i > 0:
                    prev_t = cells[i - 1].get_text().strip()
                    if t and t == prev_t:
                        cell.string = ""

        prev_row = None
        to_remove = []

        for row in rows:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text().strip() for c in cells]
            empty_count = sum(1 for t in texts if not t)
            first = texts[0] if texts else ""

            prev_first = ""
            if prev_row is not None:
                pc = prev_row.find(["th", "td"])
                if pc:
                    prev_first = pc.get_text().strip()

            is_continuation = prev_row is not None and (
                (not first and empty_count > len(cells) / 2)
                or (first and first[0].islower())
                or (prev_first and prev_first.endswith("-"))
            )

            if is_continuation:
                prev_cells = prev_row.find_all(["th", "td"])
                for i, cell in enumerate(cells):
                    t = cell.get_text().strip()
                    if t and i < len(prev_cells):
                        prev_t = prev_cells[i].get_text().strip()
                        if prev_t and prev_t.endswith("-"):
                            prev_cells[i].string = prev_t + t
                        elif prev_t:
                            prev_cells[i].string = prev_t + " " + t
                        else:
                            prev_cells[i].string = t
                to_remove.append(row)
            else:
                prev_row = row

        for row in to_remove:
            row.decompose()

        _merge_pdf_table_cols(table)


def _merge_pdf_table_cols(table):
    rows = table.find_all("tr")
    if not rows:
        return

    changed = True
    while changed:
        changed = False
        num_cols = max(len(r.find_all(["th", "td"])) for r in rows)
        if num_cols < 4:
            break

        for ci in range(num_cols - 1, 0, -1):
            col_data = []
            for row in rows:
                cells = row.find_all(["th", "td"])
                col_data.append(cells[ci].get_text().strip() if ci < len(cells) else "")

            all_empty = all(not v for v in col_data)
            if all_empty:
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if ci < len(cells):
                        cells[ci].decompose()
                changed = True
                continue

            prev_col_data = []
            for row in rows:
                cells = row.find_all(["th", "td"])
                prev_col_data.append(cells[ci - 1].get_text().strip() if ci - 1 < len(cells) else "")

            curr_filled = sum(1 for v in col_data if v)
            prev_filled = sum(1 for v in prev_col_data if v)
            if curr_filled < prev_filled and curr_filled <= len(rows) * 0.4:
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if ci < len(cells):
                        t = cells[ci].get_text().strip()
                        if t and ci - 1 < len(cells):
                            prev_t = cells[ci - 1].get_text().strip()
                            if prev_t and prev_t.endswith("-"):
                                cells[ci - 1].string = prev_t + t
                            elif prev_t:
                                cells[ci - 1].string = prev_t + " " + t
                            else:
                                cells[ci - 1].string = t
                        cells[ci].decompose()
                changed = True


def _build_pdf_toc(doc, reader_html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(reader_html, "html.parser")
    headings = []
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        hid = h.get("id")
        text = h.get_text().strip()
        stripped = re.sub(r"^\d+(\.\d+)*\s+", "", text).strip()
        headings.append((hid, text.lower(), stripped.lower()))

    toc = []
    used_ids = set()
    for level, title, _page in doc.get_toc():
        entry = {"level": min(level, 3), "title": title.strip()}
        title_lower = title.strip().lower()
        for hid, full, stripped in headings:
            if hid in used_ids:
                continue
            if title_lower == full or title_lower == stripped or stripped.startswith(title_lower):
                entry["id"] = hid
                used_ids.add(hid)
                break
        toc.append(entry)

    return toc


def _extract_docx(path: str, image_dir: str = None) -> dict:
    import mammoth

    images = []
    convert_image = None
    if image_dir:

        def convert_image(image):
            ext = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/gif": ".gif",
                "image/webp": ".webp",
            }.get(image.content_type, ".png")
            filename = f"img_{len(images)}{ext}"
            with image.open() as src, open(os.path.join(image_dir, filename), "wb") as dst:
                dst.write(src.read())
            images.append({"type": "image", "filename": filename, "alt": image.alt_text or ""})
            return {"src": filename, "alt": image.alt_text or ""}

        convert_image = mammoth.images.img_element(convert_image)

    with open(path, "rb") as f:
        result = mammoth.convert_to_html(f, convert_image=convert_image)

    reader_html, toc = _normalize_reader_headings(result.value)
    text = _html_to_plain_text(reader_html)

    if images:
        total_chars = len(text) or 1
        step = total_chars // (len(images) + 1)
        for i, img in enumerate(images):
            img["char_offset"] = step * (i + 1)
            img["total_chars"] = total_chars

    return {"text": text, "images": images, "reader_html": reader_html, "toc": toc}


def _extract_rtf(path: str, image_dir: str = None) -> dict:
    from striprtf.striprtf import rtf_to_text

    with open(path, "r", errors="ignore") as f:
        return {"text": rtf_to_text(f.read()), "images": []}
