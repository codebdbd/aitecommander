from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QDialog

from app.controllers.ui.links.link_operations import LinksUILinkOperations
from app.models.types.constants import MAX_NOTES_LENGTH
from app.models.utils.link_validators import validate_link_data
from app.utils.security.note_crypto import (
    CorruptedNotePayloadError,
    InvalidNotePasswordError,
    decrypt_note,
    encrypt_note,
    is_encrypted_note,
)
from app.utils.ui.menu_builders.links_menu_builder import LinksMenuBuilder
from app.utils.ui.menu_builders.menu_actions import MenuTexts
from app.views.widgets.link.item_builders import ItemBuildersMixin
from app.views.windows.dialogs.note_password_dialog import NotePasswordDialog


def test_encrypt_decrypt_roundtrip_unicode() -> None:
    secret_text = "Логин: admin\nПароль: SuperSecret!123 🔒\nLine 3"
    pwd = "CorrectHorseBatteryStaple"

    enc1 = encrypt_note(secret_text, pwd)
    enc2 = encrypt_note(secret_text, pwd)

    assert is_encrypted_note(enc1)
    assert is_encrypted_note(enc2)
    assert enc1 != enc2  # Random salt and nonce must produce distinct ciphertexts
    assert "SuperSecret" not in enc1

    assert decrypt_note(enc1, pwd) == secret_text
    assert decrypt_note(enc2, pwd) == secret_text


def test_decrypt_wrong_password_raises() -> None:
    enc = encrypt_note("Sensitive token", "pass123")
    with pytest.raises(InvalidNotePasswordError):
        decrypt_note(enc, "wrong_pass")


def test_decrypt_tampered_payload_raises() -> None:
    enc = encrypt_note("Sensitive token", "pass123")
    tampered = enc[:-4] + ("AAAA" if not enc.endswith("AAAA") else "BBBB")
    with pytest.raises((InvalidNotePasswordError, CorruptedNotePayloadError)):
        decrypt_note(tampered, "pass123")


def test_validate_link_data_allows_max_length_encrypted_note() -> None:
    long_note = "Я" * MAX_NOTES_LENGTH
    enc = encrypt_note(long_note, "secret")
    validate_link_data({"name": "Link", "url": "https://example.com", "notes": enc})


def test_item_builders_masks_encrypted_note() -> None:
    builder = ItemBuildersMixin()
    plain_disp, plain_tip = builder._notes_display_and_tooltip("Hello world")
    assert plain_disp == "📝 Hello world"
    assert plain_tip == "Hello world"

    enc = encrypt_note("My secret password", "pw")
    enc_disp, enc_tip = builder._notes_display_and_tooltip(enc)
    assert enc_disp.startswith("🔒")
    assert "aite_enc" not in enc_disp
    assert "My secret password" not in enc_disp
    assert enc_tip == enc_disp


def test_context_menu_shows_encrypt_or_decrypt_action(monkeypatch) -> None:
    recorded_texts: list[str] = []

    class _CapturingActions:
        def create(self, text: str, *_args, **_kwargs):
            recorded_texts.append(text)
            return SimpleNamespace(setEnabled=lambda _v: None)

    main_window = SimpleNamespace(
        settings=SimpleNamespace(get_theme=lambda: "dark"),
        links_actions=SimpleNamespace(
            show_link_dialog=lambda **_kw: None,
            open_selected_links=lambda: None,
            launch_marked_links=lambda: None,
            toggle_link_favorite=lambda _l: None,
            show_note_dialog=lambda _l: None,
            toggle_note_encryption=lambda _l: None,
        ),
        get_current_category_id=lambda: 1,
    )
    monkeypatch.setattr(
        "app.utils.ui.menu_builders.links_menu_builder.get_menu_icon",
        lambda *_a, **_kw: None,
    )

    builder = LinksMenuBuilder(SimpleNamespace(), main_window)
    builder.actions = _CapturingActions()
    monkeypatch.setattr(builder, "_count_marked_links", lambda: 0)
    monkeypatch.setattr(builder, "_is_web_link", lambda _l: False)

    fake_menu = SimpleNamespace(addAction=lambda _a: None, addSeparator=lambda: None)

    # 1. Empty note -> neither Encrypt nor Decrypt
    recorded_texts.clear()
    builder._add_link_item_actions(fake_menu, {"name": "A", "notes": ""})
    assert MenuTexts.ADD_NOTE in recorded_texts
    assert MenuTexts.ENCRYPT_NOTE not in recorded_texts
    assert MenuTexts.DECRYPT_NOTE not in recorded_texts

    # 2. Plaintext note -> Encrypt note
    recorded_texts.clear()
    builder._add_link_item_actions(fake_menu, {"name": "A", "notes": "Plain text"})
    assert MenuTexts.EDIT_NOTE in recorded_texts
    assert MenuTexts.ENCRYPT_NOTE in recorded_texts
    assert MenuTexts.DECRYPT_NOTE not in recorded_texts

    # 3. Encrypted note -> Decrypt note
    recorded_texts.clear()
    enc = encrypt_note("Plain text", "pw")
    builder._add_link_item_actions(fake_menu, {"name": "A", "notes": enc})
    assert MenuTexts.EDIT_NOTE in recorded_texts
    assert MenuTexts.DECRYPT_NOTE in recorded_texts
    assert MenuTexts.ENCRYPT_NOTE not in recorded_texts


def test_note_password_dialog_verification(qapp) -> None:
    dlg = NotePasswordDialog(
        mode="unlock",
        verify_callback=lambda pwd: pwd == "secret123",
    )
    assert dlg.password_le is not None
    dlg.password_le.setText("wrong")
    dlg._on_accept()
    assert dlg.result() != int(QDialog.DialogCode.Accepted)
    assert dlg._error_label is not None and not dlg._error_label.isHidden()

    dlg.password_le.setText("secret123")
    dlg._on_accept()
    assert dlg.result() == int(QDialog.DialogCode.Accepted)


def test_toggle_and_show_encrypted_note_workflow(monkeypatch) -> None:
    pushed_cmds: list = []
    main_window = SimpleNamespace(
        undo_stack=SimpleNamespace(push=lambda cmd: pushed_cmds.append(cmd))
    )
    ops = LinksUILinkOperations.__new__(LinksUILinkOperations)
    ops.main = main_window
    ops.business = SimpleNamespace()

    # 1. Encrypt plaintext note via toggle_note_encryption
    class _FakeEncryptPwdDialog:
        def __init__(self, mode="encrypt", **_kwargs):
            assert mode == "encrypt"

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_password(self):
            return "master_pw"

    monkeypatch.setattr(
        "app.controllers.ui.links.link_operations.NotePasswordDialog",
        _FakeEncryptPwdDialog,
    )

    link = {"id": 1, "name": "Server", "url": "https://srv", "notes": "root_pass_42"}
    ops.toggle_note_encryption(link)
    assert len(pushed_cmds) == 1
    encrypted_notes = pushed_cmds[0].new_data["notes"]
    assert is_encrypted_note(encrypted_notes)
    assert decrypt_note(encrypted_notes, "master_pw") == "root_pass_42"

    # 2. Open encrypted note in Zen NoteDialog, edit it, verify it saves re-encrypted
    link_enc = dict(link, notes=encrypted_notes)
    pushed_cmds.clear()

    class _FakeUnlockPwdDialog:
        def __init__(self, mode="unlock", verify_callback=None, **_kwargs):
            assert mode == "unlock"
            assert verify_callback is not None
            assert not verify_callback("bad_pw")
            assert verify_callback("master_pw")

        def exec(self):
            return QDialog.DialogCode.Accepted

    class _FakeNoteDialog:
        def __init__(self, initial_text="", **_kwargs):
            # Zen dialog must receive decrypted plaintext!
            assert initial_text == "root_pass_42"

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_notes_text(self):
            return "updated_pass_99"

    monkeypatch.setattr(
        "app.controllers.ui.links.link_operations.NotePasswordDialog",
        _FakeUnlockPwdDialog,
    )
    monkeypatch.setattr(
        "app.controllers.ui.links.link_operations.NoteDialog",
        _FakeNoteDialog,
    )

    ops.show_note_dialog(link_enc)
    assert len(pushed_cmds) == 1
    re_encrypted = pushed_cmds[0].new_data["notes"]
    assert is_encrypted_note(re_encrypted)
    assert decrypt_note(re_encrypted, "master_pw") == "updated_pass_99"
