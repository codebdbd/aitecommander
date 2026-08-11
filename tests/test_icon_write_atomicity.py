"""Multiprocessing test: verify PNG + metadata write atomicity.

Two or more processes run concurrently:
- WRITER(s): save a PNG via Pillow `img.save()` then write JSON metadata,
  both through `_atomic_write_bytes` / `_atomic_write_text` helpers
  (temp file + os.replace).
- READER(s): repeatedly attempt to open+verify the PNG and parse the JSON.

If any reader ever sees a corrupted PNG, invalid JSON, or an empty file,
the test fails.  Leftover .tmp files are also checked.

This isolates the *cross-process* race that `threading.Lock` cannot protect,
and validates that atomic writes eliminate partial-read corruption.
"""

from __future__ import annotations

import glob
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image
from app.utils.links.parser.favicon_cache import _file_lock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_IMG_64 = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
_PNG_64 = _make_png_bytes(_IMG_64)

_IMG_256 = Image.new("RGBA", (256, 256), (0, 128, 255, 255))
_PNG_256 = _make_png_bytes(_IMG_256)

_VARIANT_IMGS = [_IMG_64, _IMG_256]

_PNG_HEADER = b"\x89PNG\r\n\x1a\n"
_IEND_CHUNK = b"IEND"


def _is_valid_png(data: bytes) -> tuple[bool, str]:
    if not data:
        return False, "empty"
    if len(data) < 8:
        return False, f"too_short({len(data)})"
    if data[:8] != _PNG_HEADER:
        return False, f"bad_header({data[:8].hex()})"
    if _IEND_CHUNK not in data:
        return False, f"no_iend(len={len(data)})"
    return True, "ok"


def _is_valid_meta(data: str) -> tuple[bool, str]:
    try:
        obj = json.loads(data)
        if isinstance(obj, dict) and "saved_at" in obj:
            return True, "ok"
        return False, f"bad_structure({type(obj).__name__})"
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"json_error({e})"


# ---------------------------------------------------------------------------
# Atomic write helpers (mirror production code)
# ---------------------------------------------------------------------------


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(data)
        _replace_with_retry(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_text(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(text, encoding="utf-8")
        _replace_with_retry(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _replace_with_retry(src: Path, dst: Path, *, retries: int = 3, delay: float = 0.005) -> None:
    """``os.replace`` with retries for Windows PermissionError (file held open)."""
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise


# ---------------------------------------------------------------------------
# Writer (child process)
# ---------------------------------------------------------------------------


def _writer_proc(
    png_path: str,
    meta_path: str,
    stop_event,
    write_count: multiprocessing.Value,
):
    """Continuously write PNG + metadata via atomic helpers."""
    cycle = 0
    while not stop_event.is_set():
        img = _VARIANT_IMGS[cycle % len(_VARIANT_IMGS)]
        png_bytes = _make_png_bytes(img)

        meta = json.dumps(
            {"saved_at": time.time(), "cycle": cycle, "source_url": "http://test"},
            ensure_ascii=False,
            indent=2,
        )

        # Mirror production: PNG + metadata are replaced while holding
        # the same interprocess lock, so concurrent writers serialize.
        with _file_lock(f"{png_path}.lock"):
            _atomic_write_bytes(Path(png_path), png_bytes)
            _atomic_write_text(Path(meta_path), meta)

        with write_count.get_lock():
            write_count.value += 1
        cycle += 1


# ---------------------------------------------------------------------------
# Reader (child process)
# ---------------------------------------------------------------------------


def _reader_proc(
    png_path: str,
    meta_path: str,
    stop_event,
    corruption_count: multiprocessing.Value,
    empty_read_count: multiprocessing.Value,
    read_count: multiprocessing.Value,
    diagnostic_queue: multiprocessing.Queue | None = None,
):
    """Continuously try to read and validate PNG + metadata."""
    while not stop_event.is_set():
        # --- Read PNG ---
        try:
            if os.path.exists(png_path):
                with open(png_path, "rb") as f:
                    png_data = f.read()
                if png_data:
                    valid, reason = _is_valid_png(png_data)
                    if not valid:
                        with corruption_count.get_lock():
                            corruption_count.value += 1
                        if diagnostic_queue is not None and corruption_count.value <= 5:
                            diagnostic_queue.put({
                                "type": "png_corruption",
                                "reason": reason,
                                "size": len(png_data),
                                "first_16": png_data[:16].hex(),
                            })
                else:
                    with empty_read_count.get_lock():
                        empty_read_count.value += 1
        except OSError:
            pass

        # --- Read metadata ---
        try:
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta_text = f.read()
                if meta_text:
                    valid, reason = _is_valid_meta(meta_text)
                    if not valid:
                        with corruption_count.get_lock():
                            corruption_count.value += 1
                        if diagnostic_queue is not None and corruption_count.value <= 5:
                            diagnostic_queue.put({
                                "type": "meta_corruption",
                                "reason": reason,
                                "size": len(meta_text),
                                "first_100": meta_text[:100],
                            })
                else:
                    with empty_read_count.get_lock():
                        empty_read_count.value += 1
        except (OSError, UnicodeDecodeError):
            pass

        with read_count.get_lock():
            read_count.value += 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAtomicPngWrite(unittest.TestCase):
    """Verify atomic writes eliminate cross-process read corruption."""

    def _run_race(
        self,
        *,
        num_writers: int = 1,
        num_readers: int = 4,
        duration: float = 5.0,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "test_icon.png")
            meta_path = os.path.join(tmpdir, "test_icon.meta.json")

            stop_event = multiprocessing.Event()
            write_count = multiprocessing.Value("i", 0)
            read_count = multiprocessing.Value("i", 0)
            corruption_count = multiprocessing.Value("i", 0)
            empty_read_count = multiprocessing.Value("i", 0)
            diagnostic_queue = multiprocessing.Queue()

            writers = []
            for _ in range(num_writers):
                p = multiprocessing.Process(
                    target=_writer_proc,
                    args=(png_path, meta_path, stop_event, write_count),
                )
                writers.append(p)

            readers = []
            for _ in range(num_readers):
                p = multiprocessing.Process(
                    target=_reader_proc,
                    args=(
                        png_path, meta_path, stop_event,
                        corruption_count, empty_read_count, read_count,
                        diagnostic_queue,
                    ),
                )
                readers.append(p)

            for p in writers + readers:
                p.start()

            time.sleep(duration)
            stop_event.set()

            for p in writers + readers:
                p.join(timeout=10)

            writes = write_count.value
            reads = read_count.value
            corruptions = corruption_count.value
            empty_reads = empty_read_count.value

            # Check for leftover .tmp files
            tmp_files = glob.glob(os.path.join(tmpdir, "*.tmp"))

            diagnostics = []
            while not diagnostic_queue.empty():
                try:
                    diagnostics.append(diagnostic_queue.get_nowait())
                except Exception:
                    break

            print(f"\n  writers={num_writers}  readers={num_readers}")
            print(f"  writes={writes}  reads={reads}")
            print(f"  corruptions={corruptions}  empty_reads={empty_reads}")
            print(f"  leftover_tmp={len(tmp_files)}")
            if diagnostics:
                print(f"  diagnostics: {diagnostics[:3]}")

            return writes, reads, corruptions, empty_reads, tmp_files

    def test_single_writer_four_readers(self):
        """1 writer, 4 readers: zero corruption, zero empty reads, no .tmp leftovers."""
        writes, reads, corruptions, empty_reads, tmp_files = self._run_race(
            num_writers=1, num_readers=4, duration=10.0,
        )
        self.assertGreaterEqual(writes, 1, "Writer too slow, test unreliable")
        self.assertGreater(reads, 100, "Readers too slow, test unreliable")
        self.assertEqual(corruptions, 0,
                         f"Corruption: {corruptions} / {reads}")
        self.assertEqual(empty_reads, 0,
                         f"Empty reads: {empty_reads} / {reads}")
        self.assertEqual(len(tmp_files), 0,
                         f"Leftover .tmp files: {tmp_files}")

    def test_two_writers_four_readers(self):
        """2 writers, 4 readers: zero corruption, zero empty reads, no .tmp leftovers.

        This is the scenario that produced 11 corruptions with direct writes.
        """
        writes, reads, corruptions, empty_reads, tmp_files = self._run_race(
            num_writers=2, num_readers=4, duration=8.0,
        )
        self.assertGreaterEqual(writes, 5, "Writers too slow, test unreliable")
        self.assertGreater(reads, 100, "Readers too slow, test unreliable")
        self.assertEqual(corruptions, 0,
                         f"Corruption: {corruptions} / {reads}")
        self.assertEqual(empty_reads, 0,
                         f"Empty reads: {empty_reads} / {reads}")
        self.assertEqual(len(tmp_files), 0,
                         f"Leftover .tmp files: {tmp_files}")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    unittest.main()
