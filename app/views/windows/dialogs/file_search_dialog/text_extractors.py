import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

try:
    import pypdf
except ImportError:
    pypdf = None


def find_match_in_text(
    text: str,
    search_term: str,
    case_sensitive: bool = False,
    whole_words: bool = False,
) -> int:
    """Find position of search_term in text according to case and word-boundary rules."""
    if whole_words:
        flags = 0 if case_sensitive else re.IGNORECASE
        m = re.search(rf"\b{re.escape(search_term)}\b", text, flags=flags)
        return m.start() if m else -1
    if not case_sensitive:
        return text.lower().find(search_term.lower())
    return text.find(search_term)


def make_snippet(text: str, match_idx: int, match_len: int, radius: int = 40) -> str:
    """Create a cleaned single-line snippet around match position."""
    start = max(0, match_idx - radius)
    end = min(len(text), match_idx + match_len + radius)
    sub = text[start:end]
    sub = re.sub(r"<[^>]+>", " ", sub)
    clean = " ".join(sub.split())
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{clean}{suffix}".strip()


def contains_docx_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in Word .docx / .docm returning snippet."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            if "word/document.xml" not in zf.namelist():
                return False, ""
            with zf.open("word/document.xml") as f:
                tail = ""
                overlap = len(search_text)
                while chunk := f.read(256 * 1024):
                    text = tail + chunk.decode("utf-8", errors="ignore")
                    idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                    if idx != -1:
                        return True, make_snippet(text, idx, len(search_text))
                    tail = text[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def contains_docx(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in Word .docx / .docm."""
    matched, _ = contains_docx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_xlsx_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in Excel .xlsx / .xlsm returning snippet."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            if "xl/sharedStrings.xml" not in zf.namelist():
                return False, ""
            with zf.open("xl/sharedStrings.xml") as f:
                tail = ""
                overlap = len(search_text)
                while chunk := f.read(256 * 1024):
                    text = tail + chunk.decode("utf-8", errors="ignore")
                    idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                    if idx != -1:
                        return True, make_snippet(text, idx, len(search_text))
                    tail = text[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def contains_xlsx(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in Excel .xlsx / .xlsm."""
    matched, _ = contains_xlsx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_pptx_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in PowerPoint .pptx returning snippet."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            overlap = len(search_text)
            for name in zf.namelist():
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    with zf.open(name) as f:
                        tail = ""
                        while chunk := f.read(256 * 1024):
                            text = tail + chunk.decode("utf-8", errors="ignore")
                            idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                            if idx != -1:
                                return True, make_snippet(text, idx, len(search_text))
                            tail = text[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def contains_pptx(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in PowerPoint .pptx."""
    matched, _ = contains_pptx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_opendocument_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in OpenDocument returning snippet."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            if "content.xml" not in zf.namelist():
                return False, ""
            with zf.open("content.xml") as f:
                tail = ""
                overlap = len(search_text)
                while chunk := f.read(256 * 1024):
                    text = tail + chunk.decode("utf-8", errors="ignore")
                    idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                    if idx != -1:
                        return True, make_snippet(text, idx, len(search_text))
                    tail = text[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def contains_opendocument(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in OpenDocument (.odt, .ods, .odp)."""
    matched, _ = contains_opendocument_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_fb2_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in FictionBook returning snippet."""
    try:
        lower = filepath.lower()
        overlap = len(search_text)
        if lower.endswith(".zip") or lower.endswith(".fb2.zip"):
            with zipfile.ZipFile(filepath) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".fb2"):
                        with zf.open(name) as f:
                            tail = ""
                            while chunk := f.read(256 * 1024):
                                text = tail + chunk.decode("utf-8", errors="ignore")
                                idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                                if idx != -1:
                                    return True, make_snippet(text, idx, len(search_text))
                                tail = text[-overlap:] if overlap > 0 else ""
            return False, ""
        with open(filepath, "rb") as f:
            tail = ""
            while chunk := f.read(256 * 1024):
                text = tail + chunk.decode("utf-8", errors="ignore")
                idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
                if idx != -1:
                    return True, make_snippet(text, idx, len(search_text))
                tail = text[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def contains_fb2(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in FictionBook (.fb2 / .fb2.zip)."""
    matched, _ = contains_fb2_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_rtf_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """Early-exit search in Rich Text Format (.rtf) returning snippet."""
    try:
        with open(filepath, "r", encoding="latin-1", errors="ignore") as f:
            content = f.read(10 * 1024 * 1024)
        text = re.sub(r"\\[a-zA-Z]+(-?\d+)?\s?", " ", content)
        text = re.sub(r"[{}\\]", " ", text)
        idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
        if idx != -1:
            return True, make_snippet(text, idx, len(search_text))
        return False, ""
    except Exception:
        return False, ""


def contains_rtf(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """Early-exit search in Rich Text Format (.rtf)."""
    matched, _ = contains_rtf_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_pdf_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """High-speed early-exit content search in PDF file returning snippet."""
    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(filepath)
            for page in reader.pages[:500]:
                txt = page.extract_text()
                if txt:
                    idx = find_match_in_text(txt, search_text, case_sensitive, whole_words)
                    if idx != -1:
                        return True, make_snippet(txt, idx, len(search_text))
            return False, ""
        except Exception:
            pass

    try:
        with open(filepath, "rb") as f:
            data = f.read(15 * 1024 * 1024)
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
            stream_data = m.group(1)
            try:
                decomp = zlib.decompress(stream_data)
            except Exception:
                decomp = stream_data
            text = decomp.decode("latin-1", errors="ignore")
            idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
            if idx != -1:
                return True, make_snippet(text, idx, len(search_text))
        return False, ""
    except Exception:
        return False, ""


def contains_pdf(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """High-speed early-exit content search in PDF file."""
    matched, _ = contains_pdf_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def contains_ole_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool, str]:
    """Early-exit stream search in pre-2007 MS Office files returning snippet."""
    try:
        with open(filepath, "rb") as f:
            tail_u16 = ""
            tail_ansi = ""
            overlap = len(search_text)
            has_non_ascii = any(ord(c) > 127 for c in search_text)
            while chunk := f.read(256 * 1024):
                text_u16 = tail_u16 + chunk.decode("utf-16-le", errors="ignore")
                idx_u16 = find_match_in_text(text_u16, search_text, case_sensitive, whole_words)
                if idx_u16 != -1:
                    return True, make_snippet(text_u16, idx_u16, len(search_text))
                tail_u16 = text_u16[-overlap:] if overlap > 0 else ""

                text_ansi = tail_ansi + chunk.decode("cp1251", errors="ignore")
                idx_ansi = find_match_in_text(text_ansi, search_text, case_sensitive, whole_words)
                if idx_ansi != -1:
                    return True, make_snippet(text_ansi, idx_ansi, len(search_text))
                tail_ansi = text_ansi[-overlap:] if overlap > 0 else ""

                if has_non_ascii:
                    text_w1252 = chunk.decode("windows-1252", errors="ignore")
                    idx_w1252 = find_match_in_text(text_w1252, search_text, case_sensitive, whole_words)
                    if idx_w1252 != -1:
                        return True, make_snippet(text_w1252, idx_w1252, len(search_text))
        return False, ""
    except Exception:
        return False, ""


def contains_ole(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool:
    """Early-exit stream search in pre-2007 MS Office files (.doc, .xls, .ppt)."""
    matched, _ = contains_ole_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def check_document_content_with_snippet(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> tuple[bool | None, str]:
    """Detect document format and execute fast early-exit search with snippet.

    Returns (True/False, snippet) if handled by document extractors, or (None, "") if plain text.
    """
    suffix = Path(filepath).suffix.lower().lstrip(".")

    if suffix in ("docx", "docm"):
        return contains_docx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("xlsx", "xlsm"):
        return contains_xlsx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("pptx", "pptm"):
        return contains_pptx_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("odt", "ods", "odp"):
        return contains_opendocument_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("fb2",):
        return contains_fb2_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("rtf",):
        return contains_rtf_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("pdf",):
        return contains_pdf_with_snippet(filepath, search_text, case_sensitive, whole_words)
    if suffix in ("doc", "xls", "ppt"):
        return contains_ole_with_snippet(filepath, search_text, case_sensitive, whole_words)

    return None, ""


def check_document_content(
    filepath: str, search_text: str, case_sensitive: bool = False, whole_words: bool = False
) -> bool | None:
    """Detect document format and execute fast early-exit search.

    Returns True/False if handled by document extractors, or None if plain text.
    """
    matched, _ = check_document_content_with_snippet(filepath, search_text, case_sensitive, whole_words)
    return matched


def extract_docx(filepath: str) -> str | None:
    """Extract text from Word .docx file."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            if "word/document.xml" not in zf.namelist():
                return None
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
        texts = []
        for elem in tree.iter():
            if elem.tag.endswith("}t") and elem.text:
                texts.append(elem.text)
        return " ".join(texts)
    except Exception:
        return None


def extract_xlsx(filepath: str) -> str | None:
    """Extract text from Excel .xlsx file."""
    try:
        texts = []
        with zipfile.ZipFile(filepath) as zf:
            names = set(zf.namelist())
            if "xl/sharedStrings.xml" in names:
                with zf.open("xl/sharedStrings.xml") as f:
                    tree = ET.parse(f)
                for elem in tree.iter():
                    if elem.tag.endswith("}t") and elem.text:
                        texts.append(elem.text)
            for name in names:
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    with zf.open(name) as f:
                        tree = ET.parse(f)
                    for elem in tree.iter():
                        if (elem.tag.endswith("}v") or elem.tag.endswith("}t")) and elem.text:
                            texts.append(elem.text)
        return " ".join(texts) if texts else None
    except Exception:
        return None


def extract_pptx(filepath: str) -> str | None:
    """Extract text from PowerPoint .pptx file."""
    try:
        texts = []
        with zipfile.ZipFile(filepath) as zf:
            for name in sorted(zf.namelist()):
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    with zf.open(name) as f:
                        tree = ET.parse(f)
                    for elem in tree.iter():
                        if elem.tag.endswith("}t") and elem.text:
                            texts.append(elem.text)
        return " ".join(texts) if texts else None
    except Exception:
        return None


def extract_opendocument(filepath: str) -> str | None:
    """Extract text from OpenDocument (.odt, .ods, .odp) files."""
    try:
        with zipfile.ZipFile(filepath) as zf:
            if "content.xml" not in zf.namelist():
                return None
            with zf.open("content.xml") as f:
                tree = ET.parse(f)
        texts = [elem.text for elem in tree.iter() if elem.text]
        return " ".join(texts)
    except Exception:
        return None


def extract_fb2(filepath: str) -> str | None:
    """Extract text from FictionBook (.fb2 / .fb2.zip) ebook."""
    try:
        lower = filepath.lower()
        if lower.endswith(".zip") or lower.endswith(".fb2.zip"):
            with zipfile.ZipFile(filepath) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".fb2"):
                        with zf.open(name) as f:
                            tree = ET.parse(f)
                        return " ".join(e.text for e in tree.iter() if e.text)
        tree = ET.parse(filepath)
        return " ".join(e.text for e in tree.iter() if e.text)
    except Exception:
        return None


def extract_rtf(filepath: str) -> str | None:
    """Extract text from Rich Text Format (.rtf) file."""
    try:
        with open(filepath, "r", encoding="latin-1", errors="ignore") as f:
            content = f.read(5 * 1024 * 1024)
        text = re.sub(r"\\[a-zA-Z]+(-?\d+)?\s?", " ", content)
        text = re.sub(r"[{}\\]", " ", text)
        return text
    except Exception:
        return None


def extract_pdf(filepath: str) -> str | None:
    """Extract text from PDF file (pypdf or lightweight fallback)."""
    try:
        import pypdf

        reader = pypdf.PdfReader(filepath)
        parts = []
        for i, page in enumerate(reader.pages[:500]):
            txt = page.extract_text()
            if txt:
                parts.append(txt)
        return "\n".join(parts)
    except ImportError:
        pass
    except Exception:
        return None

    # Lightweight PDF stream parser without external dependencies
    try:
        with open(filepath, "rb") as f:
            data = f.read(15 * 1024 * 1024)
        texts = []
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
            stream_data = m.group(1)
            decomp = None
            try:
                decomp = zlib.decompress(stream_data)
            except Exception:
                decomp = stream_data
            for tm in re.finditer(rb"\((.*?)\)\s*T[jJ]", decomp):
                try:
                    texts.append(tm.group(1).decode("latin-1", errors="ignore"))
                except Exception:
                    pass
        return " ".join(texts) if texts else None
    except Exception:
        return None


def extract_ole_runs(filepath: str) -> str | None:
    """Extract UTF-16LE and ANSI text sequences from pre-2007 MS Office files (.doc, .xls, .ppt)."""
    try:
        with open(filepath, "rb") as f:
            data = f.read(15 * 1024 * 1024)
    except OSError:
        return None

    extracted = []
    # Both even and odd byte alignments for UTF-16LE
    for offset in (0, 1):
        try:
            u16 = data[offset:].decode("utf-16-le", errors="ignore")
            runs = re.findall(r"[\w\u0400-\u04ff\s.,;:!?\"'()\-+/%]{3,}", u16)
            extracted.extend(r.strip() for r in runs if len(r.strip()) >= 3)
        except Exception:
            pass

    # ANSI / CP1251 strings
    try:
        ansi = data.decode("cp1251", errors="ignore")
        runs_ansi = re.findall(r"[\w\u0400-\u04ff\s.,;:!?\"'()\-+/%]{4,}", ansi)
        extracted.extend(r.strip() for r in runs_ansi if len(r.strip()) >= 4)
    except Exception:
        pass

    return " ".join(extracted) if extracted else None


def extract_text_by_format(filepath: str) -> str | None:
    """Auto-detect format by extension or file signature and extract text."""
    suffix = Path(filepath).suffix.lower().lstrip(".")

    if suffix in ("docx", "docm"):
        return extract_docx(filepath)
    if suffix in ("xlsx", "xlsm"):
        return extract_xlsx(filepath)
    if suffix in ("pptx", "pptm"):
        return extract_pptx(filepath)
    if suffix in ("odt", "ods", "odp"):
        return extract_opendocument(filepath)
    if suffix in ("fb2",):
        return extract_fb2(filepath)
    if suffix in ("rtf",):
        return extract_rtf(filepath)
    if suffix in ("pdf",):
        return extract_pdf(filepath)
    if suffix in ("doc", "xls", "ppt"):
        return extract_ole_runs(filepath)

    # Magic byte checks for missing or unusual extensions
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        if header.startswith(b"PK\x03\x04"):
            # Could be docx, xlsx, pptx, odt
            return (
                extract_docx(filepath)
                or extract_xlsx(filepath)
                or extract_pptx(filepath)
                or extract_opendocument(filepath)
                or extract_fb2(filepath)
            )
        if header.startswith(b"%PDF-"):
            return extract_pdf(filepath)
        if header.startswith(b"{\\rtf"):
            return extract_rtf(filepath)
        if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return extract_ole_runs(filepath)
    except OSError:
        pass

    return None
