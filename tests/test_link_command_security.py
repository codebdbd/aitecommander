"""Integration test for link command execution security and shell injection prevention."""

import logging
import unittest

from app.utils.links.link_utils import ScriptLinkHandler, SecurityValidator


class TestLinkCommandSecurity(unittest.TestCase):
    """Verify that script link execution sanitizes shell metacharacters and prevents injection."""

    def setUp(self) -> None:
        self.logger = logging.getLogger("TestLinkCommandSecurity")
        self.handler = ScriptLinkHandler(self.logger)

    def test_sanitize_cmd_arg_escapes_metacharacters(self) -> None:
        """Verify escaping of &, |, <, >, ^, %, and double quotes."""
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo & bar"), "foo ^& bar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo | bar"), "foo ^| bar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo > bar"), "foo ^> bar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo < bar"), "foo ^< bar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo ^ bar"), "foo ^^ bar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("%USER%"), "^%USER^%")

    def test_sanitize_cmd_arg_strips_newlines(self) -> None:
        """Verify that carriage returns and line feeds are stripped to prevent newline injection."""
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("foo\r\nbar"), "foobar")
        self.assertEqual(SecurityValidator.sanitize_cmd_arg("arg\ncmd"), "argcmd")

    def test_create_batch_command_applies_sanitization(self) -> None:
        """Verify that _create_batch_command sanitizes all arguments."""
        args = ["arg1 & calc.exe", 'val" && whoami', "foo|dir>test.txt"]
        cmd = self.handler._create_batch_command("C:\\scripts\\run.bat", args)

        self.assertTrue(cmd.startswith("cmd.exe"))
        self.assertNotIn("start ", cmd)
        self.assertIn('"C:\\scripts\\run.bat"', cmd)
        self.assertIn("arg1 ^& calc.exe", cmd)
        self.assertIn('val\\" ^&^& whoami', cmd)
        self.assertIn("foo^|dir^>test.txt", cmd)
    def test_escape_cmd_token_doubles_quotes_and_strips_newlines(self) -> None:
        """Verify that escape_cmd_token strips newlines and doubles quotes."""
        self.assertEqual(SecurityValidator.escape_cmd_token("foo\r\nbar"), '"foobar"')
        self.assertEqual(SecurityValidator.escape_cmd_token('val"whoami'), '"val""whoami"')
        self.assertEqual(SecurityValidator.escape_cmd_token(r"C:\R&D files\x.txt"), r'"C:\R&D files\x.txt"')

    def test_build_cmd_command_wraps_in_quotes_safely(self) -> None:
        """Verify that build_cmd_command produces valid cmd.exe /k wrapped command line."""
        tokens = ["python.exe", "test.py", "50% off", "arg with space"]
        cmd = SecurityValidator.build_cmd_command(tokens, keep_open=True)
        self.assertTrue(cmd.startswith("cmd.exe /k "))
        self.assertIn('"python.exe"', cmd)
        self.assertIn('"test.py"', cmd)
        self.assertIn('"50% off"', cmd)
        self.assertIn('"arg with space"', cmd)

    def test_python_keep_open_uses_cmd_wrapper_safely(self) -> None:
        """Verify that Python script with keep-open builds a safe cmd.exe command without mangling args."""
        self.handler._py_keep_open = True
        self.handler.python_path = "C:\\Python\\python.exe"
        cmd = self.handler._create_python_command("C:\\scripts\\run.py", [r"C:\R&D files\x.txt", "50% off"])
        self.assertIsInstance(cmd, str)
        self.assertTrue(cmd.startswith("cmd.exe /k "))
        self.assertIn(r'"C:\R&D files\x.txt"', cmd)
        self.assertNotIn(r"R^&D", cmd)
        self.assertIn('"50% off"', cmd)

    def test_wsh_keep_open_uses_cmd_wrapper_safely(self) -> None:
        """Verify that VBScript with keep-open builds a safe cmd.exe command."""
        self.handler._batch_keep_open = True
        cmd = self.handler._create_wsh_command("C:\\scripts\\test.vbs", ["arg1 & calc.exe"])
        self.assertIsInstance(cmd, str)
        self.assertTrue(cmd.startswith("cmd.exe /k "))
        self.assertIn('"//NoLogo"', cmd)
        self.assertIn('"C:\\scripts\\test.vbs"', cmd)
        self.assertIn('"arg1 & calc.exe"', cmd)

    def test_get_link_type_from_path_treats_js_as_file(self) -> None:
        """Verify that .js files are recognized as LinkType.FILE rather than SCRIPT."""
        import tempfile

        from app.utils.links.link_utils import LinkType, get_link_type_from_path

        with tempfile.NamedTemporaryFile(suffix=".js") as tf:
            lt = get_link_type_from_path(tf.name)
            self.assertEqual(lt, LinkType.FILE)

        with tempfile.NamedTemporaryFile(suffix=".ps1") as tf:
            lt = get_link_type_from_path(tf.name)
            self.assertEqual(lt, LinkType.SCRIPT)

