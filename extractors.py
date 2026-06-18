import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.md', '.txt', '.rtf', '.html', '.htm'}


def extract_text(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    extractors = {
        '.txt': _extract_txt,
        '.md': _extract_md,
        '.html': _extract_html,
        '.htm': _extract_html,
        '.pdf': _extract_pdf,
        '.docx': _extract_docx,
        '.rtf': _extract_rtf,
    }
    fn = extractors.get(ext)
    if not fn:
        return None
    try:
        return fn(file_path)
    except Exception as e:
        print(f"Extraction error for {file_path}: {e}")
        return None


def _extract_txt(path: str) -> str:
    with open(path, 'r', errors='ignore') as f:
        return f.read()


def _extract_md(path: str) -> str:
    with open(path, 'r', errors='ignore') as f:
        text = f.read()
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_html(path: str) -> str:
    from bs4 import BeautifulSoup
    with open(path, 'r', errors='ignore') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    return soup.get_text(separator=' ', strip=True)


def _extract_pdf(path: str) -> str:
    import pymupdf
    doc = pymupdf.open(path)
    pages = []
    for page in doc:
        text = page.get_text()
        if text and text.strip():
            pages.append(text.strip())
    doc.close()
    return '\n\n'.join(pages)


def _extract_docx(path: str) -> str:
    import docx
    doc = docx.Document(path)
    return '\n\n'.join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_rtf(path: str) -> str:
    from striprtf.striprtf import rtf_to_text
    with open(path, 'r', errors='ignore') as f:
        return rtf_to_text(f.read())
