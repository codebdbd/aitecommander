
from __future__ import annotations

import os
from pathlib import Path
import pytest

from app.views.windows.dialogs.file_search_dialog.common import (
    check_file_content,
    detect_and_read_text,
    is_probably_binary,
    matches_criteria,
)
from app.views.windows.dialogs.file_search_dialog.search_worker import FileSearchWorker


def test_is_probably_binary_extensions():
    assert is_probably_binary('test.exe') is True
    assert is_probably_binary('test.dll') is True
    assert is_probably_binary('test.bin') is True
    assert is_probably_binary('test.pyc') is True
    assert is_probably_binary('test.txt') is False
    assert is_probably_binary('test.py') is False


def test_is_probably_binary_null_bytes(tmp_path):
    bin_file = tmp_path / 'sample.dat'
    bin_file.write_bytes(b'Some header\x00\x00\x00data')
    assert is_probably_binary(str(bin_file)) is True

    txt_file = tmp_path / 'sample.txt'
    txt_file.write_text('Hello world text file', encoding='utf-8')
    assert is_probably_binary(str(txt_file)) is False


def test_detect_and_read_text_encodings(tmp_path):
    cyrillic_text = 'Привет мир! Тестовая строка кириллицы.'

    cp1251_file = tmp_path / 'cp1251.txt'
    cp1251_file.write_bytes(cyrillic_text.encode('cp1251'))

    read_back = detect_and_read_text(str(cp1251_file))
    assert 'Привет мир' in read_back

    cp866_file = tmp_path / 'cp866.txt'
    cp866_file.write_bytes(cyrillic_text.encode('cp866'))

    read_back_866 = detect_and_read_text(str(cp866_file))
    assert 'Привет мир' in read_back_866


def test_check_file_content_with_encoding_override(tmp_path):
    text = 'Тестовое содержимое файла для проверки кодировки.'
    cp1251_file = tmp_path / 'test_doc.txt'
    cp1251_file.write_bytes(text.encode('cp1251'))

    config_auto = {'content': 'проверки'}
    assert check_file_content(config_auto, str(cp1251_file)) is True

    config_override = {'content': 'проверки', 'content_encoding_override': 'cp1251'}
    assert check_file_content(config_override, str(cp1251_file)) is True


def test_search_worker_constraints(tmp_path):
    root = tmp_path / 'search_root'
    sub1 = root / 'level1'
    sub2 = sub1 / 'level2'
    sub2.mkdir(parents=True)

    f1 = root / 'a.txt'
    f1.write_text('content A', encoding='utf-8')

    f2 = sub1 / 'b.log'
    f2.write_text('content B', encoding='utf-8')

    f3 = sub2 / 'c.txt'
    f3.write_text('content C', encoding='utf-8')

    # 1. Depth constraint: max_depth=1 (root + 1 level only, sub2 should be skipped)
    worker = FileSearchWorker({
        'root': str(root),
        'pattern': '*.*',
        'regex_name': '',
        'max_depth': 1,
    })
    results = []
    worker.signals.results_batch.connect(lambda batch: results.extend(batch))
    worker.run()

    found_files = [Path(r[0]).name for r in results]
    assert 'a.txt' in found_files
    assert 'b.log' in found_files
    assert 'c.txt' not in found_files

    # 2. Allowed extensions constraint: only txt
    worker_ext = FileSearchWorker({
        'root': str(root),
        'pattern': '*.*',
        'regex_name': '',
        'allowed_exts': ['txt'],
    })
    results_ext = []
    worker_ext.signals.results_batch.connect(lambda batch: results_ext.extend(batch))
    worker_ext.run()

    found_ext = [Path(r[0]).name for r in results_ext]
    assert 'a.txt' in found_ext
    assert 'c.txt' in found_ext
    assert 'b.log' not in found_ext
