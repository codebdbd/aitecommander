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

        self.assertEqual(cmd[0], "cmd.exe")
        self.assertEqual(cmd[1], "/c")
        self.assertEqual(cmd[2], "start")
        self.assertEqual(cmd[3], '""')
        self.assertEqual(cmd[4], "C:\\scripts\\run.bat")
        self.assertEqual(cmd[5], "arg1 ^& calc.exe")
        self.assertEqual(cmd[6], 'val\\" ^&^& whoami')
        self.assertEqual(cmd[7], "foo^|dir^>test.txt")
