from __future__ import annotations

import pytest

from app.utils.links.link_utils import SecurityValidator


def test_is_safe_url_allows_wikipedia_and_parentheses() -> None:
    wiki_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
    assert SecurityValidator.is_safe_url(wiki_url) is True


def test_is_safe_url_allows_valid_rfc3986_subdelims() -> None:
    assert SecurityValidator.is_safe_url("https://example.com/api?$filter=name eq 'test'") is False
    assert SecurityValidator.is_safe_url("https://example.com/api?$filter=name%20eq%20'test'") is True
    assert SecurityValidator.is_safe_url("https://example.com/path;session=123?a=1&b=2") is True
    assert SecurityValidator.is_safe_url("http://sub.domain.org/foo(bar)baz") is True


def test_is_safe_url_rejects_unsafe_urls() -> None:
    assert SecurityValidator.is_safe_url("") is False
    assert SecurityValidator.is_safe_url("javascript:alert(1)") is False
    assert SecurityValidator.is_safe_url("data:text/html,<html>") is False
    assert SecurityValidator.is_safe_url("https://example.com/<script>") is False
    assert SecurityValidator.is_safe_url("https://example.com/test|evil") is False
    assert SecurityValidator.is_safe_url("https://example.com/test`evil`") is False
    assert SecurityValidator.is_safe_url("https://example.com/test\r\nevil") is False
    assert SecurityValidator.is_safe_url("https://example.com/test\0evil") is False


def test_is_safe_path_allows_parentheses_and_rejects_dangerous_chars() -> None:
    assert SecurityValidator.is_safe_path("C:\\Program Files (x86)\\App\\app.exe") is True
    assert SecurityValidator.is_safe_path("C:\\App\\file(1).txt") is True
    assert SecurityValidator.is_safe_path("C:\\App\\file|bad.exe") is False
    assert SecurityValidator.is_safe_path("C:\\App\\file;bad.exe") is False
    assert SecurityValidator.is_safe_path("C:\\App\\file>bad.exe") is False
