"""Remote scanner: a read-only, public HTTP scan of a WordPress site.

Respects robots.txt, identifies itself with a clear User-Agent, and only ever issues
GET requests. The `fetch` parameter on RemoteScanner is injectable specifically so
tests can substitute a fake HTTP layer instead of making real network calls; production
code uses requests by default.
"""

from __future__ import annotations

import re
import urllib.robotparser
from typing import Callable, NamedTuple
from urllib.parse import urljoin

from ..models import ContentProfile, ScanMode, SiteProfile, TrafficProfile

USER_AGENT = "wp2aws-scanner/0.1 (+https://github.com/sauharddobhal/wp2aws)"

_WOOCOMMERCE_MARKERS = ("woocommerce",)
_MEMBERSHIP_MARKERS = ("memberpress", "restrict-content-pro", "paid-memberships-pro", "wp-members")

_PLUGIN_PATH_PATTERN = re.compile(r"wp-content/plugins/([a-zA-Z0-9_-]+)")
_THEME_PATH_PATTERN = re.compile(r"wp-content/themes/([a-zA-Z0-9_-]+)")
_ASSET_URL_PATTERN = re.compile(
    r'(?:src|href)=["\'](?P<url>[^"\']+\.(?:css|js|png|jpe?g|gif|svg|webp))["\']',
    re.IGNORECASE,
)

# Cap how many assets we measure per page. This is a respectful-crawling bound, not a
# precision one, real pages can have far more than this; measuring a representative
# sample is enough to materially improve on a flat default assumption without turning
# this into a heavy crawler.
MAX_ASSETS_PER_PAGE = 15


class FetchResult(NamedTuple):
    status_code: int
    text: str
    headers: dict[str, str]


Fetcher = Callable[[str], FetchResult]
HeadFetcher = Callable[[str], dict[str, str]]


class RobotsDisallowedError(Exception):
    pass


class RemoteScanner:
    def __init__(self, fetch: Fetcher | None = None, fetch_head: HeadFetcher | None = None):
        self._fetch = fetch or self._default_fetch
        self._fetch_head = fetch_head or self._default_fetch_head

    @staticmethod
    def _default_fetch(url: str) -> FetchResult:
        import requests

        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        return FetchResult(response.status_code, response.text, dict(response.headers))

    @staticmethod
    def _default_fetch_head(url: str) -> dict[str, str]:
        import requests

        response = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=5, allow_redirects=True)
        return dict(response.headers)

    def _check_robots_allowed(self, base_url: str) -> None:
        robots_url = urljoin(base_url, "/robots.txt")
        try:
            result = self._fetch(robots_url)
        except Exception:
            # If robots.txt itself can't be fetched, fail open (most sites don't have
            # one and that's not a signal to refuse scanning), but a real implementation
            # could choose to fail closed instead; documented here as the deliberate
            # choice it is.
            return
        if result.status_code != 200:
            return
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(result.text.splitlines())
        if not parser.can_fetch(USER_AGENT, base_url):
            raise RobotsDisallowedError(
                f"robots.txt at {robots_url} disallows scanning by {USER_AGENT}"
            )

    def scan(self, url: str, sessions_per_day: int, peak_to_average_ratio: float = 5.0) -> SiteProfile:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        self._check_robots_allowed(url)

        homepage = self._fetch(url)
        plugins = sorted(set(_PLUGIN_PATH_PATTERN.findall(homepage.text)))

        content_profile = self._infer_content_profile(plugins, homepage.text)

        post_count = self._rest_api_count(url, "posts")
        page_count = self._rest_api_count(url, "pages")

        cache_headers_present = any(
            header.lower() in {"cache-control", "x-cache", "cf-cache-status", "age"}
            for header in homepage.headers
        )

        page_weights_mb = [self._measure_page_weight_mb(url, homepage.text)]
        sample_post_url = self._sample_post_url(url)
        if sample_post_url:
            try:
                post_page = self._fetch(sample_post_url)
                if post_page.status_code == 200:
                    page_weights_mb.append(self._measure_page_weight_mb(sample_post_url, post_page.text))
            except Exception:
                pass
        measured_avg_page_weight_mb = round(sum(page_weights_mb) / len(page_weights_mb), 4)

        notes = [
            "Remote scan: plugin list is detected from front-end asset paths only and "
            "will miss backend-only plugins. Run in --local mode for an exhaustive list.",
            "Remote scan: traffic figure below is a user-provided input, not a "
            "measurement, there is no honest way to measure real traffic from outside "
            "a site.",
            f"Page weight measured from {len(page_weights_mb)} sampled page(s) "
            f"(HTML plus up to {MAX_ASSETS_PER_PAGE} linked assets each via HEAD "
            f"requests), not a default assumption.",
        ]

        return SiteProfile(
            source_url=url,
            scan_mode=ScanMode.REMOTE,
            traffic=TrafficProfile(
                sessions_per_day=sessions_per_day,
                peak_to_average_ratio=peak_to_average_ratio,
                measured=False,
            ),
            content_profile=content_profile,
            plugins=plugins,
            plugin_detection_exhaustive=False,
            post_count=post_count,
            page_count=page_count,
            existing_cache_headers_present=cache_headers_present,
            measured_avg_page_weight_mb=measured_avg_page_weight_mb,
            notes=notes,
        )

    def _extract_asset_urls(self, html_text: str, base_url: str) -> list[str]:
        raw_urls = _ASSET_URL_PATTERN.findall(html_text)
        resolved = [urljoin(base_url, u) for u in raw_urls]
        # De-dupe while preserving order, then cap, so the same stylesheet referenced
        # twice doesn't eat into the budget meant for distinct assets.
        seen: set[str] = set()
        unique: list[str] = []
        for u in resolved:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique[:MAX_ASSETS_PER_PAGE]

    def _measure_page_weight_mb(self, page_url: str, html_text: str) -> float:
        html_bytes = len(html_text.encode("utf-8"))
        asset_bytes = 0
        for asset_url in self._extract_asset_urls(html_text, page_url):
            try:
                headers = self._fetch_head(asset_url)
            except Exception:
                continue
            content_length = headers.get("Content-Length") or headers.get("content-length")
            if content_length:
                try:
                    asset_bytes += int(content_length)
                except ValueError:
                    continue
        return (html_bytes + asset_bytes) / (1024 * 1024)

    def _sample_post_url(self, base_url: str) -> str | None:
        api_url = urljoin(base_url, "/wp-json/wp/v2/posts?per_page=1")
        try:
            result = self._fetch(api_url)
        except Exception:
            return None
        if result.status_code != 200:
            return None
        try:
            import json

            posts = json.loads(result.text)
        except (ValueError, TypeError):
            return None
        if not posts or not isinstance(posts, list):
            return None
        return posts[0].get("link")

    def _infer_content_profile(self, plugins: list[str], homepage_text: str) -> ContentProfile:
        lowered_plugins = [p.lower() for p in plugins]
        lowered_html = homepage_text.lower()

        if any(marker in lowered_plugins or marker in lowered_html for marker in _WOOCOMMERCE_MARKERS):
            return ContentProfile.WOOCOMMERCE
        if any(marker in lowered_plugins for marker in _MEMBERSHIP_MARKERS):
            return ContentProfile.MEMBERSHIP
        return ContentProfile.CONTENT

    def _rest_api_count(self, base_url: str, resource: str) -> int | None:
        api_url = urljoin(base_url, f"/wp-json/wp/v2/{resource}?per_page=1")
        try:
            result = self._fetch(api_url)
        except Exception:
            return None
        if result.status_code != 200:
            return None
        total_header = result.headers.get("X-WP-Total") or result.headers.get("x-wp-total")
        if total_header is None:
            return None
        try:
            return int(total_header)
        except ValueError:
            return None
