"""
Thin wrapper for backward-compat: delegates to parser.fetcher.fetch_web_link_info.
"""

from app.utils.links.parser.fetcher import fetch_web_link_info as fetch_web_link_info

__all__ = ["fetch_web_link_info"]
