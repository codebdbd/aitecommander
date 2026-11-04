"""Service for creating, reading, and managing inline scripts inside Aite Commander."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

from app.config_data.runtime_config import runtime_app_config as app_config

logger = logging.getLogger(__name__)

SUPPORTED_SCRIPT_EXTENSIONS: tuple[str, ...] = (
    ".ps1",
    ".bat",
    ".py",
    ".pyw",
    ".vbs",
    ".cmd",
)

_FENCE_RE = re.compile(
    r"^\s*```(?P<lang>[a-zA-Z0-9_+-]*)\s*\r?\n(?P<body>[\s\S]*?)\r?\n\s*```\s*$"
)

_LANG_TO_EXT: dict[str, str] = {
    "ps1": ".ps1",
    "powershell": ".ps1",
    "pwsh": ".ps1",
    "posh": ".ps1",
    "bat": ".bat",
    "batch": ".bat",
    "cmd": ".cmd",
    "dos": ".bat",
    "py": ".py",
    "python": ".py",
    "python3": ".py",
    "pyw": ".pyw",
    "vbs": ".vbs",
    "vbscript": ".vbs",
}


class ScriptStorageService:
    """Manages script files created directly inside the application."""

    @classmethod
    def get_scripts_dir(cls, ensure_exists: bool = True) -> Path:
        """Return the managed scripts directory in user AppData."""
        try:
            if hasattr(app_config.paths, "get_scripts_dir"):
                scripts_dir = Path(app_config.paths.get_scripts_dir())
            else:
                scripts_dir = Path(app_config.paths.get_user_data_dir()) / "scripts"
        except Exception:
            scripts_dir = Path.home() / ".aitecommander" / "scripts"
        if ensure_exists:
            scripts_dir.mkdir(parents=True, exist_ok=True)
        return scripts_dir

    @classmethod
    def is_managed_script(cls, path: str | Path | None) -> bool:
        """Check whether the given file path is inside the managed scripts directory."""
        if not path:
            return False
        try:
            target = Path(path).resolve()
            scripts_dir = cls.get_scripts_dir(ensure_exists=False).resolve()
            return scripts_dir in target.parents
        except Exception:
            return False

    @classmethod
    def clean_and_detect_script(cls, raw_text: str) -> tuple[str, str | None]:
        """Strip optional AI Markdown code fences and detect script extension.

        Returns:
            (cleaned_code, detected_extension_or_None)
        """
        if not raw_text:
            return "", None

        text = raw_text.strip()
        fence_match = _FENCE_RE.match(text)
        detected_ext: str | None = None

        if fence_match:
            lang = (fence_match.group("lang") or "").strip().lower()
            text = fence_match.group("body")
            detected_ext = _LANG_TO_EXT.get(lang)

        if detected_ext is None:
            detected_ext = cls.detect_extension_from_code(text)

        return text, detected_ext

    @classmethod
    def detect_extension_from_code(cls, code: str) -> str | None:
        """Heuristically detect script extension (.ps1, .bat, .py, .vbs) from code content."""
        if not code or not code.strip():
            return None

        stripped = code.strip()
        first_line = stripped.splitlines()[0].strip().lower()

        # 1. Shebang or explicit header checks
        if first_line.startswith("#!") and "python" in first_line:
            return ".py"
        if (
            first_line.startswith("@echo ")
            or first_line.startswith("rem ")
            or first_line.startswith("::")
        ):
            return ".bat"
        if first_line.startswith("#requires") or first_line.startswith("<#"):
            return ".ps1"

        # 2. Batch signatures
        if re.search(
            r"(?im)^(?:\s*@?echo\s+(?:off|on)\b|\s*setlocal\b|\s*chcp\s+\d+|\s*goto\s+:?\w+|\s*::\s+)",
            stripped,
        ):
            return ".bat"

        # 3. PowerShell signatures
        if re.search(
            r"(?im)(?:\b(?:Write-Host|Write-Output|Write-Error|Write-Warning|Get-ChildItem|Get-Item|"
            r"Get-Process|Get-Content|Set-Content|Set-Location|Invoke-RestMethod|Invoke-WebRequest|"
            r"Start-Process|New-Item|Remove-Item|Test-Path|Select-Object|Where-Object|ForEach-Object)\b|"
            r"\$PSVersionTable\b|\$PSScriptRoot\b|\$ErrorActionPreference\b|\[CmdletBinding\s*\(|"
            r"^\s*param\s*\()",
            stripped,
        ):
            return ".ps1"

        # 4. Python signatures
        if re.search(
            r"(?m)(?:^\s*(?:import|from)\s+[a-zA-Z_][a-zA-Z0-9_.]*|^\s*def\s+[a-zA-Z_]\w*\s*\(|"
            r"^\s*class\s+[a-zA-Z_]\w*|if\s+__name__\s*==\s*['\"]__main__['\"])",
            stripped,
        ):
            return ".py"

        # 5. VBScript signatures
        if re.search(
            r"(?im)(?:\bWScript\.(?:Echo|Shell|Quit|CreateObject)\b|\bCreateObject\s*\(\s*\"|"
            r"^\s*Option\s+Explicit\b|\bMsgBox\s+)",
            stripped,
        ):
            return ".vbs"

        return None

    @classmethod
    def suggest_script_name(cls, code: str) -> str:
        """Extract a human-friendly script name from the leading comment if available."""
        if not code or not code.strip():
            return ""

        for line in code.strip().splitlines()[:5]:
            s = line.strip()
            if not s:
                continue
            # Ignore technical directives
            low = s.lower()
            if (
                low.startswith("#!")
                or low.startswith("# -*-")
                or low.startswith("#requires")
                or low.startswith("@echo")
                or low.startswith("setlocal")
                or low.startswith("chcp")
            ):
                continue

            comment_body = ""
            if s.startswith("#"):
                comment_body = s.lstrip("#").strip()
            elif s.startswith("::"):
                comment_body = s.lstrip(":").strip()
            elif low.startswith("rem "):
                comment_body = s[4:].strip()
            elif s.startswith("'"):
                comment_body = s.lstrip("'").strip()

            if comment_body:
                # Clean punctuation and cap length
                clean = re.sub(r"[#*`~_=\-]+$", "", comment_body).strip(" :.-—")
                if 2 <= len(clean) <= 60:
                    return clean
                break
            else:
                break

        return ""

    @classmethod
    def _sanitize_stem(cls, name_hint: str) -> str:
        """Build a safe filename stem from a link/script name."""
        raw = (name_hint or "").strip()
        if not raw:
            return "script"
        # Replace characters invalid on Windows filesystems
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw)
        cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
        if not cleaned:
            return "script"
        return cleaned[:48]

    @classmethod
    def save_script(
        cls,
        code: str,
        ext: str = ".ps1",
        name_hint: str = "",
        existing_path: str | Path | None = None,
    ) -> Path:
        """Save script code to disk with appropriate Windows encoding and line endings.

        - PowerShell (.ps1) uses UTF-8 with BOM (`utf-8-sig`) for Windows PowerShell 5.1 compatibility.
        - Batch (.bat/.cmd) and others use UTF-8 with CRLF line endings on Windows.
        """
        norm_ext = (ext or ".ps1").strip().lower()
        if not norm_ext.startswith("."):
            norm_ext = f".{norm_ext}"
        if norm_ext not in SUPPORTED_SCRIPT_EXTENSIONS:
            norm_ext = ".ps1"

        scripts_dir = cls.get_scripts_dir()
        target_path: Path | None = None

        if existing_path:
            try:
                candidate = Path(existing_path)
                if (
                    candidate.is_file()
                    or cls.is_managed_script(candidate)
                    or candidate.parent.is_dir()
                ):
                    if candidate.suffix.lower() == norm_ext:
                        target_path = candidate
                    elif cls.is_managed_script(candidate):
                        target_path = candidate.with_suffix(norm_ext)
            except Exception:
                target_path = None

        if target_path is None:
            stem = cls._sanitize_stem(name_hint)
            short_id = uuid.uuid4().hex[:8]
            target_path = scripts_dir / f"{stem}_{short_id}{norm_ext}"

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # For .bat and .cmd: ensure UTF-8 console output for non-ASCII characters
        script_code = code
        if norm_ext in (".bat", ".cmd") and not script_code.isascii():
            if "chcp" not in script_code.lower():
                script_code = f"@chcp 65001 >nul\r\n{script_code}"

        # Normalize line endings to CRLF for Windows scripts
        normalized_lines = script_code.replace("\r\n", "\n").replace("\r", "\n")
        if norm_ext in (".ps1", ".bat", ".cmd", ".vbs"):
            payload_text = normalized_lines.replace("\n", "\r\n")
        else:
            payload_text = normalized_lines

        if norm_ext == ".ps1":
            encoding = "utf-8-sig"
        elif norm_ext == ".vbs":
            encoding = "utf-16"
        else:
            encoding = "utf-8"

        # If existing managed file is renamed to a different extension, remove the old file
        if existing_path:
            try:
                candidate = Path(existing_path)
                if candidate.is_file() and candidate.resolve() != target_path.resolve():
                    candidate.unlink(missing_ok=True)
            except Exception:
                pass

        # Atomic write via temporary file
        tmp_target = target_path.with_name(
            f"{target_path.name}.{uuid.uuid4().hex[:6]}.tmp"
        )
        try:
            tmp_target.write_text(payload_text, encoding=encoding, newline="")
            tmp_target.replace(target_path)
        except Exception:
            if tmp_target.exists():
                tmp_target.unlink(missing_ok=True)
            target_path.write_text(payload_text, encoding=encoding, newline="")

        return target_path.resolve()

    @classmethod
    def read_script(cls, path: str | Path) -> tuple[str, str]:
        """Read script text and extension from an existing file."""
        import platform

        p = Path(path)
        ext = p.suffix.lower() if p.suffix else ".ps1"
        raw_bytes = p.read_bytes()
        if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
            try:
                return raw_bytes.decode("utf-16").replace("\r\n", "\n"), ext
            except UnicodeDecodeError:
                pass

        # Detect Windows system OEM code page (e.g. cp866, cp437)
        oem_enc: str = "cp866"
        if platform.system() == "Windows":
            try:
                import ctypes

                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                if oem_cp:
                    oem_enc = f"cp{oem_cp}"
            except Exception:
                oem_enc = "cp866"

        if ext in (".bat", ".cmd"):
            encodings = ("utf-8-sig", "utf-8", oem_enc, "cp1251")
        else:
            encodings = ("utf-8-sig", "utf-8", "cp1251", oem_enc)

        for enc in encodings:
            try:
                text = raw_bytes.decode(enc)
                return text.replace("\r\n", "\n"), ext
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n"), ext

    @classmethod
    def find_unused_managed_scripts(
        cls, active_urls: Iterable[str | Path]
    ) -> list[Path]:
        """Find scripts inside the managed scripts directory that are not referenced by active links.

        Args:
            active_urls: Collection of paths or URLs currently referenced in the database.

        Returns:
            Sorted list of unreferenced managed script paths.
        """
        scripts_dir = cls.get_scripts_dir(ensure_exists=False)
        if not scripts_dir.is_dir():
            return []

        active_resolved: set[Path] = set()
        for raw_url in active_urls:
            if not raw_url:
                continue
            try:
                active_resolved.add(Path(raw_url).resolve())
            except Exception:
                continue

        unused: list[Path] = []
        try:
            for item in scripts_dir.iterdir():
                if not item.is_file():
                    continue
                if item.name.startswith(".") or ".tmp" in item.name.lower():
                    continue
                if item.suffix.lower() not in SUPPORTED_SCRIPT_EXTENSIONS:
                    continue
                try:
                    if item.resolve() not in active_resolved:
                        unused.append(item.resolve())
                except Exception:
                    continue
        except OSError as e:
            logger.warning("Error reading scripts directory: %s", e)

        unused.sort()
        return unused

    @classmethod
    def purge_unused_managed_scripts(cls, active_urls: Iterable[str | Path]) -> int:
        """Purge managed scripts not referenced by any active link.

        Returns:
            Count of successfully deleted script files.
        """
        unused = cls.find_unused_managed_scripts(active_urls)
        deleted_count = 0
        for script_path in unused:
            try:
                script_path.unlink(missing_ok=True)
                deleted_count += 1
                logger.info("Purged unused managed script: %s", script_path)
            except OSError as e:
                logger.warning(
                    "Failed to purge unused managed script %s: %s", script_path, e
                )
        return deleted_count
