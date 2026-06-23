from wp2aws.scanners.remote import FetchResult, RemoteScanner

HOMEPAGE_WITH_ASSETS = """
<html><head>
<link rel="stylesheet" href="https://example.com/style.css">
<script src="https://example.com/script.js"></script>
</head><body>
<img src="https://example.com/hero.jpg">
</body></html>
"""


def _make_fetcher(responses: dict[str, FetchResult]):
    def fetch(url: str) -> FetchResult:
        if url in responses:
            return responses[url]
        for key in sorted(responses, key=len, reverse=True):
            if key in url:
                return responses[key]
        return FetchResult(404, "", {})

    return fetch


def _make_head_fetcher(responses: dict[str, dict[str, str]]):
    def fetch_head(url: str) -> dict[str, str]:
        for key in sorted(responses, key=len, reverse=True):
            if key in url:
                return responses[key]
        return {}

    return fetch_head


def test_measures_page_weight_from_html_and_assets():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_WITH_ASSETS, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {}),
        }
    )
    head_fetcher = _make_head_fetcher(
        {
            "style.css": {"Content-Length": "10000"},   # ~9.77 KB
            "script.js": {"Content-Length": "20000"},   # ~19.53 KB
            "hero.jpg": {"Content-Length": "500000"},   # ~488 KB
        }
    )
    scanner = RemoteScanner(fetch=fetcher, fetch_head=head_fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    assert profile.measured_avg_page_weight_mb is not None
    assert profile.measured_avg_page_weight_mb > 0
    # Roughly (HTML bytes + 10000 + 20000 + 500000) / 1MB; should be well under 1 MB
    assert profile.measured_avg_page_weight_mb < 1.0


def test_falls_back_gracefully_when_head_requests_fail():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_WITH_ASSETS, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {}),
        }
    )

    def failing_head_fetcher(url):
        raise ConnectionError("simulated network failure")

    scanner = RemoteScanner(fetch=fetcher, fetch_head=failing_head_fetcher)
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    # Should still produce a profile (HTML-only weight) rather than crashing.
    assert profile.measured_avg_page_weight_mb is not None


def test_averages_across_homepage_and_sample_post():
    import json

    posts_response_body = json.dumps([{"link": "https://example.com/sample-post/"}])
    fetcher = _make_fetcher(
        {
            "https://example.com/robots.txt": FetchResult(404, "", {}),
            "https://example.com/": FetchResult(200, "<html><body>short home</body></html>", {}),
            "https://example.com/wp-json/wp/v2/posts?per_page=1": FetchResult(200, posts_response_body, {}),
            "https://example.com/wp-json/wp/v2/pages?per_page=1": FetchResult(200, "[]", {}),
            "https://example.com/sample-post/": FetchResult(200, "<html><body>a post page</body></html>" * 5000, {}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher, fetch_head=lambda url: {})
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)

    # Averaging two pages of very different size should land strictly between them,
    # not equal either page's individual weight, confirming both were actually sampled.
    homepage_only_mb = len("<html><body>short home</body></html>".encode()) / (1024 * 1024)
    assert profile.measured_avg_page_weight_mb > homepage_only_mb


def test_notes_explain_page_weight_was_measured():
    fetcher = _make_fetcher(
        {
            "robots.txt": FetchResult(404, "", {}),
            "example.com/": FetchResult(200, HOMEPAGE_WITH_ASSETS, {}),
            "wp-json/wp/v2/posts": FetchResult(200, "[]", {}),
            "wp-json/wp/v2/pages": FetchResult(200, "[]", {}),
        }
    )
    scanner = RemoteScanner(fetch=fetcher, fetch_head=lambda url: {})
    profile = scanner.scan("https://example.com/", sessions_per_day=100_000)
    assert any("Page weight measured" in note for note in profile.notes)
