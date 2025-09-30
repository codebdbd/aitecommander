import importlib



def reload_lp():
    from app.utils.links import link_parser as lp

    importlib.reload(lp)
    return lp


def test_get_default_icon_logs_warning_on_resolve_error(monkeypatch, caplog):
    lp = reload_lp()

    monkeypatch.setattr(lp, "resolve_icon_for_link", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")))

    caplog.set_level("WARNING")
    out = lp._get_default_icon("file", object())
    assert out == ""
    assert any("_get_default_icon failed for type=file" in rec.message for rec in caplog.records)


def test_extract_icon_from_exe_makedirs_oserror(monkeypatch, caplog, tmp_path):
    lp = reload_lp()

    exe = str(tmp_path / "app.exe")
    icons_dir = str(tmp_path / "icons")

    # Bypass validations
    monkeypatch.setattr(lp, "_validate_exe_path", lambda p: True)
    monkeypatch.setattr(lp.os.path, "exists", lambda p: False)
    monkeypatch.setattr(lp.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))

    caplog.set_level("ERROR")
    res = lp._extract_icon_from_exe(exe, icons_dir)
    assert res is None
    assert any("Cannot create icons directory" in rec.message for rec in caplog.records)


def test_extract_icon_from_exe_win32_error(monkeypatch, caplog, tmp_path):
    lp = reload_lp()

    exe = str(tmp_path / "app.exe")
    icons_dir = str(tmp_path / "icons")

    # Ensure path exists branch
    monkeypatch.setattr(lp, "_validate_exe_path", lambda p: True)
    monkeypatch.setattr(lp.os.path, "exists", lambda p: True)

    # Force win32gui.ExtractIconEx to raise win32ui.error
    class W32Err(Exception):
        pass

    monkeypatch.setattr(lp, "win32ui", type("W", (), {"error": W32Err}))
    def raise_extract(*_a, **_k):
        raise W32Err("w32")
    monkeypatch.setattr(lp.win32gui, "ExtractIconEx", raise_extract)

    caplog.set_level("ERROR")
    out = lp._extract_icon_from_exe(exe, icons_dir)
    assert out is None
    assert any("Win32 error extracting icon" in rec.message for rec in caplog.records)


def test_handle_chromeapp_icon_copy_oserror(monkeypatch, caplog, tmp_path):
    lp = reload_lp()

    icons_dir = str(tmp_path / "icons")
    lnk_info = {"args": "--app-id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "icon_path": str(tmp_path / "src.png")}

    # cached icon invalid
    monkeypatch.setattr(lp, "is_valid_icon_file", lambda p: False)
    # icon source exists
    monkeypatch.setattr(lp.os.path, "exists", lambda p: True)
    # makedirs ok
    monkeypatch.setattr(lp.os, "makedirs", lambda *a, **k: None)
    # copyfile raises
    def boom(*_a, **_k):
        raise OSError("copy denied")
    monkeypatch.setattr(lp.shutil, "copyfile", boom)

    caplog.set_level("ERROR")
    out = lp._handle_chromeapp_icon(lnk_info, icons_dir)
    assert out is None
    assert any("Failed to copy chromeapp icon" in rec.message for rec in caplog.records)
