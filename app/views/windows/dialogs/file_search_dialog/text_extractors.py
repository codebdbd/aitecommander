import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path


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
