"""Integration test for icon path and filename sanitization."""

import unittest
from app.utils.links.parser.domain import base_domain, sanitize_domain_for_filename
from app.utils.ui.icon.path_service import icon_path_service, _sanitize_domain_for_filename


class TestIconPathSanitization(unittest.TestCase):
    """Verify that domain strings with colons, ports, and Windows-forbidden chars are sanitized."""

    def test_sanitize_domain_for_filename(self) -> None:
        """Verify replacement of invalid NTFS characters in domain strings."""
        self.assertEqual(sanitize_domain_for_filename("localhost:8080"), "localhost_8080")
        self.assertEqual(sanitize_domain_for_filename("192.168.1.1:5000"), "192_168_1_1_5000")
        self.assertEqual(sanitize_domain_for_filename("test:foo*bar?baz"), "test_foo_bar_baz")

    def test_base_domain_port_stripping(self) -> None:
        """Verify that base_domain strips port numbers."""
        self.assertEqual(base_domain("http://localhost:8080"), "localhost")
        self.assertEqual(base_domain("http://127.0.0.1:3000/app"), "127.0.0.1")
        self.assertEqual(base_domain("https://example.com:8443/test"), "example.com")

    def test_path_service_sanitizes_colon_paths(self) -> None:
        """Verify that PathService never produces filenames containing colons."""
        filename = _sanitize_domain_for_filename("localhost:8080")
        self.assertNotIn(":", filename)
        self.assertEqual(filename, "localhost_8080")

        # Verify get_web_icon_path for web URL with port
        web_icon_path = icon_path_service.get_web_icon_path("localhost:8080")
        self.assertNotIn(":", web_icon_path.name)
        self.assertTrue(web_icon_path.name.endswith(".png"))
        self.assertEqual(web_icon_path.name, "web_localhost_8080.png")
