import importlib
import contextlib
import os


def reload_lp():
    from app.utils.links import link_parser as lp

    importlib.reload(lp)
    return lp


def test_get_name_for_link_type_logs_and_returns_unknown_on_error(caplog):
    lp = reload_lp()

    caplog.set_level("ERROR")
    # Use link_type=program and provide lnk_info with non-string path to provoke exception
    res = lp._get_name_for_link_type("program", "C:/somepath", {"path": object()})
    assert res == "Unknown"
    assert any(
        "Error getting name for link_type=" in rec.message for rec in caplog.records
    )


def test_handle_folder_icon_logs_and_uses_default_on_resolve_failure(monkeypatch, caplog):
    lp = reload_lp()

    # resolve_icon_for_link fails
    monkeypatch.setattr(lp, "resolve_icon_for_link", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    # force default icon path to be stable and non-empty
    monkeypatch.setattr(lp, "_get_default_icon", lambda *_a, **_k: "def.png")

    caplog.set_level("DEBUG")
    out = lp._handle_folder_icon(config=None)
    assert out == "def.png"
    # Debug message about resolve failure must be present
    assert any(
        "folder icon resolve failed" in rec.message for rec in caplog.records
    )


def test_handle_file_icon_logs_on_os_error(monkeypatch, tmp_path, caplog):
    lp = reload_lp()

    path = str(tmp_path / "file.ext")

    def fake_exists(p):
        return False

    monkeypatch.setattr(os.path, "exists", fake_exists)
    # Trigger makedirs failure
    monkeypatch.setattr(lp.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))

    caplog.set_level("ERROR")
    icon = lp._handle_file_icon(path, str(tmp_path / "icons"))
    assert icon is None
    assert any("Failed to extract file icon for path=" in rec.message for rec in caplog.records)


def test_get_icon_for_link_type_logs_and_fallback_on_helper_error(monkeypatch, caplog, tmp_path):
    lp = reload_lp()

    # program icon helper raises
    monkeypatch.setattr(lp, "_handle_program_icon", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    # default icon path stable
    monkeypatch.setattr(lp, "_get_default_icon", lambda *a, **k: "default.png")
    # ensure validity check on final result passes
    monkeypatch.setattr(lp, "is_valid_icon_file", lambda p: p == "default.png")

    caplog.set_level("ERROR")
    icon = lp._get_icon_for_link_type("program", "C:/app.exe", {}, object(), str(tmp_path))
    assert icon == "default.png"
    assert any("Error getting icon for link_type=" in rec.message for rec in caplog.records)


def test_parse_lnk_runtime_error_logged(monkeypatch, caplog, tmp_path):
    lp = reload_lp()

    lnk = str(tmp_path / "a.lnk")
    tmp_path.joinpath("a.lnk").write_text("dummy")

    # Replace com_context to raise at entry
    @contextlib.contextmanager
    def bad_context():
        raise RuntimeError("com fail")
        yield  # pragma: no cover

    monkeypatch.setattr(lp, "com_context", bad_context)

    caplog.set_level("ERROR")
    res = lp._parse_lnk(lnk)
    assert res == {}
    assert any("Error parsing .ln" in rec.message for rec in caplog.records)
