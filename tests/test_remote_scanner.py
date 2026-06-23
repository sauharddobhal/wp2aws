import pytest

from wp2aws.models import ContentProfile
from wp2aws.scanners.remote import FetchResult, RemoteScanner, RobotsDisallowedError

HOMEPAGE_HTML = """
<html><head>
<link rel="stylesheet" href="https://example.com/wp-content/themes/astra/style.css">
<script src="https://example.com/wp-content/plugins/contact-form-7/script.js"></script>
<script src="https://example.com/wp-content/plugins/yoast-seo/script.js"></script>
</head><body>Hello world</body></html>
"""

WOOCOMMERCE_HTML = HOMEPAGE_HTML.replace(
    "</head>",
    '<script src="https://example.com/wp-content/plugins/woocommerce/script.js"></script></head>',
)


def _make_fetcher(responses: dict[str, FetchResult]):
    def fetch(url: str) -> FetchResult:
        # Check longer keys first so a specific path (e.g. "wp-json/wp/v2/posts")
        # matches before a shorter, more generic one (e.g. "example.com/") that also
        # happens to be a substring of the same URL.
        for key in sorted(responses, key=len, reverse=True):
            if key in url:
                return responses[key]
        return FetchResult(404, "", {})

    return fetch


def test_scan_detects_plugins_from_asset_paths():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_HTML, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {"X-WP-Total": "42"}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {"X-WP-Total": "10"}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    assert "contact-form-7" in profile.plugins
    assert "yoast-seo" in profile.plugins
    assert profile.plugin_detection_exhaustive is False


def test_scan_reads_post_and_page_counts_from_rest_api():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_HTML, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {"X-WP-Total": "123"}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {"X-WP-Total": "7"}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    assert profile.post_count == 123
    assert profile.page_count == 7


def test_scan_detects_woocommerce_and_lowers_content_profile():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, WOOCOMMERCE_HTML, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {"X-WP-Total": "5"}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {"X-WP-Total": "5"}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    assert profile.content_profile == ContentProfile.WOOCOMMERCE


def test_scan_raises_when_robots_txt_disallows_scanner():
    disallow_robots = "User-agent: wp2aws-scanner/0.1 (+https://github.com/sauharddobhal/wp2aws)\nDisallow: /\n"
    # robotparser matches on product token; use a generic disallow-all to exercise the path
    generic_disallow_robots = "User-agent: *\nDisallow: /\n"
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(200, generic_disallow_robots, {}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    with pytest.raises(RobotsDisallowedError):
        scanner.scan("https://example.com/", sessions_per_day=100_000)


def test_scan_proceeds_when_robots_txt_missing():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_HTML, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {"X-WP-Total": "1"}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {"X-WP-Total": "1"}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)
    assert profile is not None


def test_traffic_is_marked_not_measured_in_remote_mode():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_HTML, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {"X-WP-Total": "1"}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {"X-WP-Total": "1"}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)
    assert profile.traffic.measured is False
    assert any("not a measurement" in note or "not a" in note for note in profile.notes)
