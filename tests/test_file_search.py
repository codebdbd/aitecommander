
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

    # 3. Default full depth: no max_depth specified -> searches all levels
    worker_default = FileSearchWorker({
        'root': str(root),
        'pattern': '*.*',
        'regex_name': '',
    })
    results_all = []
    worker_default.signals.results_batch.connect(lambda batch: results_all.extend(batch))
    worker_default.run()

    found_all = [Path(r[0]).name for r in results_all]
    assert 'a.txt' in found_all
    assert 'b.log' in found_all
    assert 'c.txt' in found_all


def test_content_search_office_formats(tmp_path):
    import zipfile
    import zlib

    # 1. DOCX
    docx_file = tmp_path / 'sample.docx'
    with zipfile.ZipFile(str(docx_file), 'w') as zf:
        zf.writestr(
            'word/document.xml',
            '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Конфіденційний звіт 2026</w:t></w:r></w:p></w:body></w:document>',
        )
    assert check_file_content({'content': 'конфіденційний'}, str(docx_file)) is True
    assert check_file_content({'content': 'неіснуючий'}, str(docx_file)) is False

    # 2. XLSX
    xlsx_file = tmp_path / 'sample.xlsx'
    with zipfile.ZipFile(str(xlsx_file), 'w') as zf:
        zf.writestr(
            'xl/sharedStrings.xml',
            '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Прибуток за квартал</t></si></sst>',
        )
    assert check_file_content({'content': 'прибуток'}, str(xlsx_file)) is True

    # 3. PPTX
    pptx_file = tmp_path / 'sample.pptx'
    with zipfile.ZipFile(str(pptx_file), 'w') as zf:
        zf.writestr(
            'ppt/slides/slide1.xml',
            '<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Презентація стратегії</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
        )
    assert check_file_content({'content': 'стратегії'}, str(pptx_file)) is True

    # 4. ODT
    odt_file = tmp_path / 'sample.odt'
    with zipfile.ZipFile(str(odt_file), 'w') as zf:
        zf.writestr(
            'content.xml',
            '<?xml version="1.0" encoding="UTF-8"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Документ OpenOffice LibreOffice</text:p></office:text></office:body></office:document-content>',
        )
    assert check_file_content({'content': 'libreoffice'}, str(odt_file)) is True

    # 5. FB2
    fb2_file = tmp_path / 'sample.fb2'
    fb2_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><body><section><p>Розділ перший: пригода</p></section></body></FictionBook>',
        encoding='utf-8',
    )
    assert check_file_content({'content': 'пригода'}, str(fb2_file)) is True

    # 6. RTF
    rtf_file = tmp_path / 'sample.rtf'
    rtf_file.write_text(
        r'{\rtf1\ansi\deff0 {\fonttbl {\f0 Times;}}\f0 Hello \b Important Contract \b0 \par}',
        encoding='ascii',
    )
    assert check_file_content({'content': 'important contract'}, str(rtf_file)) is True

    # 7. PDF stream
    pdf_content = b'BT /F1 12 Tf (Financial Summary Report) Tj ET'
    pdf_compressed = zlib.compress(pdf_content)
    pdf_file = tmp_path / 'sample.pdf'
    pdf_file.write_bytes(
        b'%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n'
        + pdf_compressed
        + b'\nendstream\nendobj\n%%EOF'
    )
    assert check_file_content({'content': 'Financial Summary'}, str(pdf_file)) is True

    # 8. DOC (OLE2 UTF-16LE text runs)
    doc_file = tmp_path / 'old_contract.doc'
    ole_header = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 50
    ole_text = 'Договір постачання обладнання 2026'
    doc_file.write_bytes(ole_header + ole_text.encode('utf-16-le') + b'\x00\x00')
    assert check_file_content({'content': 'постачання'}, str(doc_file)) is True

    # 9. Markdown (.md)
    md_file = tmp_path / 'README.md'
    md_file.write_text(
        '# Aite Commander\n\nШвидкий файловий менеджер із пошуком по вмісту.',
        encoding='utf-8',
    )
    assert check_file_content({'content': 'файловий менеджер'}, str(md_file)) is True
    assert check_file_content({'content': 'невідомий текст'}, str(md_file)) is False

