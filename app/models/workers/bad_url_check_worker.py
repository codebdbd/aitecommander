"""Worker для фоновой проверки доступности веб-ссылок."""

from __future__ import annotations

import logging
import socket
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.models.types.link_type import LinkType

if TYPE_CHECKING:
    from app.models.database import Database

logger = logging.getLogger(__name__)

_TR_CONTEXT = "BadUrlCheckWorker"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class BadUrlCheckSignals(QObject):
    """Signals for BadUrlCheckWorker."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    bad_url_found = pyqtSignal(dict)  # {id, url, error, category_path, hierarchy, ...}
    finished = pyqtSignal(list)  # list of bad URLs
    error = pyqtSignal(str)  # error message


class BadUrlCheckWorker(QRunnable):
    """Background worker for checking web link availability.

    Checks all web links in the database for availability.
    Uses parallel processing for faster checking.
    """

    # Error categories (by priority)
    ERROR_DNS_FAILED = "DNS Resolution Failed"
    ERROR_404 = "404 Not Found"
    ERROR_NO_SSL = "No SSL (HTTP only)"
    ERROR_UNREACHABLE = "Connection Failed"

    def __init__(
        self,
        db: Database,
        max_workers: int = 10,
        timeout: int = 5,
        check_ssl: bool = True,
    ):
        """
        Args:
            db: Database instance
            max_workers: Number of parallel threads for URL checking (recommended: 10-20)
            timeout: Connection timeout in seconds (recommended: 5-10)
            check_ssl: Whether to check HTTPS availability (False = faster)
        """
        super().__init__()
        self.db = db
        self.max_workers = max_workers
        self.timeout = timeout
        self.check_ssl = check_ssl
        self.signals = BadUrlCheckSignals()
        self._is_cancelled = False
        self._cancel_event = threading.Event()
        self._executor: ThreadPoolExecutor | None = None

    def cancel(self):
        """Cancel task execution."""
        self._is_cancelled = True
        self._cancel_event.set()
        executor = self._executor
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[bad_url_check] Executor shutdown failed during cancel: %s", exc
                )
        logger.info("[bad_url_check] Cancellation requested")

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise CancelledError()

    def _find_all_web_links(self) -> list[dict]:
        """Find all web links, deduplicated by URL.

        Returns:
            List of dicts, one per unique URL.  Each dict has:
            - ``url``: the URL string
            - ``link_ids``: list of all DB link IDs sharing this URL
            - ``link_id``: alias for the first ID (backward compat)
            - ``name``: name from the first link
            - ``category_id``: category from the first link
        """
        self._raise_if_cancelled()
        try:
            query = """
                SELECT l.id, l.url, l.name, l.category_id
                FROM link l
                WHERE l.type = ?
                ORDER BY l.id ASC
            """
            rows = self.db.connection.execute(query, (LinkType.WEB.value,)).fetchall()

            # Group by URL
            url_groups: dict[str, dict] = {}
            for row in rows:
                data = dict(row)
                url = data["url"]
                if url in url_groups:
                    url_groups[url]["link_ids"].append(data["id"])
                else:
                    url_groups[url] = {
                        "url": url,
                        "link_ids": [data["id"]],
                        "link_id": data["id"],
                        "name": data.get("name", ""),
                        "category_id": data.get("category_id"),
                    }

            unique = list(url_groups.values())
            logger.info(
                "[bad_url_check] Found %s total links, %s unique URLs",
                len(rows),
                len(unique),
            )
            return unique
        except Exception as e:
            logger.error("Failed to query web links: %s", e, exc_info=True)
            return []

    def _get_category_hierarchy(self, category_id: int | None) -> dict[str, Any]:
        """Return hierarchy metadata (names + icons) for specified category."""
        default_path = QCoreApplication.translate("BadUrlCheckWorker", "No Category")
        if not category_id:
            return {
                "path": default_path,
                "sphere_name": "",
                "sphere_icon_path": "",
                "section_name": "",
                "section_icon_path": "",
                "category_name": "",
                "category_icon_path": "",
            }

        try:
            query = """
                SELECT
                    c.name AS category_name,
                    c.icon_path AS category_icon,
                    s.name AS section_name,
                    s.icon_path AS section_icon,
                    sp.name AS sphere_name,
                    sp.icon_path AS sphere_icon
                FROM category c
                LEFT JOIN section s ON c.section_id = s.id
                LEFT JOIN sphere sp ON s.sphere_id = sp.id
                WHERE c.id = ?
            """
            row = self.db.connection.execute(query, (category_id,)).fetchone()
            if not row:
                logger.warning("Category ID %s not found in database", category_id)
                missing_path = QCoreApplication.translate("BadUrlCheckWorker", "Category #{0} (not found)").format(category_id)
                return {
                    "path": missing_path,
                    "sphere_name": "",
                    "sphere_icon_path": "",
                    "section_name": "",
                    "section_icon_path": "",
                    "category_name": "",
                    "category_icon_path": "",
                }

            row_data = dict(row)

            category_name = row_data.get("category_name") or ""
            section_name = row_data.get("section_name") or ""
            sphere_name = row_data.get("sphere_name") or ""

            parts = [part for part in (sphere_name, section_name, category_name) if part]
            path = " / ".join(parts) if parts else category_name or default_path

            return {
                "path": path,
                "sphere_name": sphere_name,
                "sphere_icon_path": row_data.get("sphere_icon") or "",
                "section_name": section_name,
                "section_icon_path": row_data.get("section_icon") or "",
                "category_name": category_name,
                "category_icon_path": row_data.get("category_icon") or "",
            }
        except Exception as e:
            logger.error(
                "Failed to get category hierarchy for %s: %s", category_id, e, exc_info=True
            )
            fallback = QCoreApplication.translate("BadUrlCheckWorker", "Error (ID: {0})").format(category_id)
            return {
                "path": fallback,
                "sphere_name": "",
                "sphere_icon_path": "",
                "section_name": "",
                "section_icon_path": "",
                "category_name": "",
                "category_icon_path": "",
            }

    def _check_https_available(self, https_url: str) -> bool:
        """Check if HTTPS version of URL is available with retry.
        
        Args:
            https_url: HTTPS URL to check
            
        Returns:
            True if HTTPS is available (2xx-3xx status), False otherwise
        """
        import time
        import urllib.request
        from urllib.error import HTTPError, URLError
        
        # Try HEAD first, then GET if HEAD fails
        for method in ["HEAD", "GET"]:
            self._raise_if_cancelled()
            try:
                req = urllib.request.Request(https_url, method=method)
                req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
                
                # Use longer timeout for GET
                timeout = 5 if method == "GET" else self.timeout
                
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    # Accept 2xx and 3xx (redirects are OK)
                    if 200 <= response.status < 400:
                        logger.debug("[bad_url_check] HTTPS available via %s: %s", method, https_url)
                        return True
                return False
            except HTTPError as e:
                if e.code == 404:
                    # Confirmed 404 - no need to try GET
                    return False
                # Other errors - try GET if this was HEAD
                if method == "HEAD":
                    continue
                return False
            except (URLError, socket.timeout):
                # Connection failed - try GET if this was HEAD
                if method == "HEAD":
                    time.sleep(0.5)  # Brief pause before GET
                    continue
                # GET also failed - HTTPS not available
                return False
            except Exception:
                # Unexpected error - try GET if this was HEAD
                if method == "HEAD":
                    continue
                return False
        
        return False
    
    def _verify_404_with_get(self, url: str) -> tuple[bool, str]:
        """Verify 404 with GET request (fallback when HEAD returns 404).
        
        Args:
            url: URL to check
            
        Returns:
            Tuple (is_reachable, error_message)
        """
        import time
        
        # Try GET with longer timeout and retry
        for attempt in range(2):  # 2 attempts
            self._raise_if_cancelled()
            try:
                import urllib.request
                from urllib.error import HTTPError, URLError
                
                if attempt > 0:
                    time.sleep(1)  # Wait 1 sec before retry
                
                req = urllib.request.Request(url, method="GET")
                # Add full browser headers to avoid blocking
                req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
                req.add_header("Accept-Language", "en-US,en;q=0.9")
                req.add_header("Accept-Encoding", "gzip, deflate, br")
                req.add_header("Connection", "keep-alive")
                req.add_header("Upgrade-Insecure-Requests", "1")
                
                # Use longer timeout for GET (5 sec instead of 3)
                get_timeout = max(5, self.timeout)
                with urllib.request.urlopen(req, timeout=get_timeout) as response:
                    if 200 <= response.status < 400:
                        # Page is OK (HEAD was blocked, but GET works)
                        logger.debug("[bad_url_check] GET confirmed page OK for %s (status=%s)", url, response.status)
                        return True, ""
                    elif response.status == 404:
                        # Confirmed 404
                        logger.info("[bad_url_check] GET confirmed 404 for %s", url)
                        return False, self.ERROR_404
                    else:
                        # Other codes - not critical
                        logger.debug("[bad_url_check] GET returned non-critical status %s for %s", response.status, url)
                        return True, ""
                        
            except HTTPError as e:
                if e.code == 404:
                    # Confirmed 404
                    logger.info("[bad_url_check] GET HTTPError confirmed 404 for %s", url)
                    return False, self.ERROR_404
                # Retry on other errors
                if attempt == 0:
                    continue
                return True, ""
                
            except (URLError, socket.timeout):
                # Retry on connection errors; repeated failures mean the URL is unreachable
                if attempt == 0:
                    continue
                logger.info("[bad_url_check] GET connection failed for %s", url)
                return False, self.ERROR_UNREACHABLE
                
            except Exception:
                # Unknown error - retry once
                if attempt == 0:
                    continue
                logger.info("[bad_url_check] GET failed for %s", url)
                return False, self.ERROR_UNREACHABLE
        
        # All attempts failed
        return False, self.ERROR_UNREACHABLE
    
    def _parse_url(self, url: str):
        """Parse URL and return ParseResult or None on invalid input."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return None
            return parsed
        except Exception:
            return None

    def _dns_check(self, domain: str) -> bool:
        """Return True if DNS resolves the domain, False otherwise."""
        try:
            socket.gethostbyname(domain)
            return True
        except socket.gaierror:
            return False

    def _head_check_and_followups(self, url: str, is_http: bool) -> tuple[bool, str]:
        """Perform HEAD request and required follow-ups (GET confirm, HTTPS availability)."""
        import urllib.request
        from urllib.error import HTTPError, URLError

        try:
            self._raise_if_cancelled()
            req = urllib.request.Request(url, method="HEAD")
            # Add full browser headers to avoid blocking
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
            req.add_header("Accept-Language", "en-US,en;q=0.9")
            req.add_header("Accept-Encoding", "gzip, deflate, br")
            req.add_header("Connection", "keep-alive")
            req.add_header("Upgrade-Insecure-Requests", "1")

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if 200 <= response.status < 400:
                    # Original URL works - evaluate HTTPS for HTTP links
                    if is_http and self.check_ssl:
                        https_url = url.replace("http://", "https://", 1)
                        if self._check_https_available(https_url):
                            return True, ""
                        return False, self.ERROR_NO_SSL
                    return True, ""
                if response.status == 404:
                    # Confirm with GET: some sites block HEAD
                    return self._verify_404_with_get(url)
                # Other codes (403, 500) - not critical
                return True, ""

        except HTTPError as e:
            if e.code == 404:
                return self._verify_404_with_get(url)
            # Other HTTP errors - not critical
            return True, ""
        except (URLError, socket.timeout):
            # Connection failed - try GET before giving up
            get_result = self._verify_404_with_get(url)
            if not get_result[0]:
                return get_result
            if url.startswith("https://") and self.check_ssl:
                return False, self.ERROR_NO_SSL
            return True, ""
        except Exception:
            logger.debug("[bad_url_check] HEAD failed for %s", url, exc_info=True)
            return False, self.ERROR_UNREACHABLE

    def _check_url(self, url: str) -> tuple[bool, str]:
        """Check URL availability (3 levels of checking).

        Args:
            url: Full URL to check

        Returns:
            Tuple (is_reachable, error_message)
        """
        try:
            self._raise_if_cancelled()
            parsed = self._parse_url(url)
            if parsed is None:
                # Invalid URL format - skip it (not critical)
                return True, ""

            # Level 1: DNS check (original domain only)
            if not self._dns_check(parsed.netloc):
                return False, self.ERROR_DNS_FAILED

            # Level 2 & 3: HEAD + follow-ups
            is_http = url.startswith("http://")
            return self._head_check_and_followups(url, is_http)

        except Exception as e:
            logger.debug("Failed to check URL %s: %s", url, e)
            return True, ""

    def _check_link(self, link: dict) -> list[dict] | None:
        """Check a deduplicated URL and emit bad_url_found for every link sharing it.

        Args:
            link: Dict with ``url``, ``link_ids``, ``name``, ``category_id``

        Returns:
            List of bad_url_info dicts (one per link ID) or None if reachable.
        """
        if self._cancel_event.is_set():
            raise CancelledError()

        url = link["url"]
        link_ids = link["link_ids"]

        # Check URL (3 levels: DNS, 404, SSL)
        is_reachable, error = self._check_url(url)

        if not is_reachable:
            self._raise_if_cancelled()

            # Extract domain once
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = QCoreApplication.translate("BadUrlCheckWorker", "unknown")

            # Emit one bad_url_found signal per link ID
            results = []
            for link_id in link_ids:
                bad_url_info = {
                    "id": link_id,
                    "url": url,
                    "name": link.get("name", ""),
                    "error": error,
                    "category_path": "",
                    "category_id": link.get("category_id"),
                    "domain": domain,
                    "hierarchy": {},
                }
                results.append(bad_url_info)

            logger.info(
                "[bad_url_check] Bad URL found: %s (%s) — affects %s links",
                url[:80],
                error,
                len(link_ids),
            )

            return results

        return None

    def run(self):
        """Main task execution method."""
        try:
            logger.info("[bad_url_check] Starting bad URL check worker")

            links = self._find_all_web_links()
            total = len(links)
            if total == 0:
                logger.info("[bad_url_check] No web links found")
                self.signals.finished.emit([])
                return

            logger.info("[bad_url_check] Found %s web links to check", total)
            self._emit_start_progress(total)

            bad_urls, checked = self._check_links_parallel(links, total)

            if self._is_cancelled:
                logger.info("[bad_url_check] Cancelled by user")
                self.signals.finished.emit(bad_urls)
                return

            sphere_stats = self._aggregate_sphere_stats(bad_urls)
            logger.info(
                "[bad_url_check] Completed: checked=%s, bad_links=%s",
                checked,
                len(bad_urls),
            )
            logger.info("[bad_url_check] Bad links by sphere: %s", sphere_stats)
            self.signals.finished.emit(bad_urls)

        except Exception as e:
            logger.error("[bad_url_check] Unexpected error: %s", e, exc_info=True)
            self.signals.error.emit(QCoreApplication.translate("BadUrlCheckWorker", "Error: {0}").format(e))

    # --- Helpers to reduce complexity of run() ---
    def _emit_start_progress(self, total: int) -> None:
        self.signals.progress.emit(
            0,
            total,
            QCoreApplication.translate("BadUrlCheckWorker", "Checking {0} links...").format(total),
        )

    def _check_links_parallel(self, links: list[dict], total: int) -> tuple[list[dict], int]:
        bad_urls: list[dict] = []
        checked = 0
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._executor = executor
        try:
            future_to_link = {executor.submit(self._check_link, link): link for link in links}
            for future in as_completed(future_to_link):
                if self._is_cancelled:
                    logger.debug("[bad_url_check] Cancelling %s pending tasks", len(future_to_link))
                    for f in future_to_link:
                        if not f.done():
                            f.cancel()
                    break

                link = future_to_link[future]
                try:
                    results = future.result()
                    if results:
                        # results is a list of bad_url_info dicts (one per link ID)
                        for info in results:
                            bad_urls.append(info)
                            self.signals.bad_url_found.emit(info)
                    checked += 1
                    self.signals.progress.emit(
                        checked,
                        total,
                        QCoreApplication.translate("BadUrlCheckWorker", "Checked {0}/{1} (issues: {2})").format(checked, total, len(bad_urls)),
                    )
                except CancelledError:
                    logger.debug("[bad_url_check] Future cancelled for URL %s", link.get("url", "?"))
                    break
                except Exception as e:
                    logger.warning(
                        "[bad_url_check] Exception checking URL %s: %s", link.get("url", "?"), e
                    )
                    checked += 1
        finally:
            shutdown_wait = not self._is_cancelled
            cancel_pending = self._is_cancelled
            try:
                executor.shutdown(wait=shutdown_wait, cancel_futures=cancel_pending)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[bad_url_check] Executor shutdown failed during cleanup: %s", exc
                )
            self._executor = None
        return bad_urls, checked

    def _aggregate_sphere_stats(self, bad_urls: list[dict]) -> dict[str, int]:
        sphere_stats: dict[str, int] = {}
        for bad_url in bad_urls:
            category_path = bad_url.get("category_path", "")
            parts = [p.strip() for p in category_path.split("/")]
            sphere = (
                parts[0]
                if len(parts) >= 1
                else QCoreApplication.translate("BadUrlCheckWorker", "Unknown")
            )
            sphere_stats[sphere] = sphere_stats.get(sphere, 0) + 1
        return sphere_stats


__all__ = ["BadUrlCheckWorker", "BadUrlCheckSignals"]
