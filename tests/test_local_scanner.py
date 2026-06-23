import json

from wp2aws.models import ContentProfile
from wp2aws.scanners.local import LocalScanner, parse_access_log

SAMPLE_ACCESS_LOG = "\n".join(
    [
        '10.0.0.1 - - [01/Jun/2026:08:00:01 +0000] "GET / HTTP/1.1" 200 5123 "-" "Mozilla/5.0"',
        '10.0.0.2 - - [01/Jun/2026:08:00:02 +0000] "GET /about HTTP/1.1" 200 3211 "-" "Mozilla/5.0"',
        '10.0.0.3 - - [01/Jun/2026:09:00:01 +0000] "GET / HTTP/1.1" 200 5123 "-" "Mozilla/5.0"',
        '10.0.0.4 - - [01/Jun/2026:09:00:02 +0000] "GET / HTTP/1.1" 200 5123 "-" "Googlebot/2.1"',
        '10.0.0.5 - - [01/Jun/2026:09:00:03 +0000] "GET /blog HTTP/1.1" 200 4000 "-" "Mozilla/5.0"',
        '10.0.0.6 - - [01/Jun/2026:09:00:04 +0000] "GET /blog HTTP/1.1" 200 4000 "-" "Mozilla/5.0"',
    ]
)


def test_parse_access_log_counts_total_requests():
    stats = parse_access_log(SAMPLE_ACCESS_LOG)
    assert stats.total_requests == 6


def test_parse_access_log_filters_bots_from_human_fraction():
    stats = parse_access_log(SAMPLE_ACCESS_LOG)
    # 1 of 6 requests is from Googlebot
    assert stats.human_request_fraction == round(5 / 6, 3)


def test_parse_access_log_computes_peak_hour_ratio():
    stats = parse_access_log(SAMPLE_ACCESS_LOG)
    # hour 08: 2 requests, hour 09: 4 requests -> average 3/hr, peak 4/hr
    assert stats.peak_hour_to_average_ratio == round(4 / 3, 2)


def test_parse_access_log_handles_empty_input():
    stats = parse_access_log("")
    assert stats.total_requests == 0
    assert stats.requests_per_day_estimate == 0.0


def test_parse_access_log_ignores_unparseable_lines():
    stats = parse_access_log("garbage line that is not a log entry\n" + SAMPLE_ACCESS_LOG)
    assert stats.total_requests == 6


def _fake_command_runner(responses: dict[tuple, str]):
    def run(args: list[str]) -> str:
        key = tuple(args)
        for resp_key, resp_value in responses.items():
            if resp_key == key[: len(resp_key)]:
                return resp_value
        raise RuntimeError(f"No fake response configured for command: {args}")

    return run


def test_get_plugins_parses_wp_cli_json_output():
    plugin_json = json.dumps([{"name": "yoast-seo"}, {"name": "contact-form-7"}])
    runner = _fake_command_runner({("wp", "plugin", "list", "--format=json"): plugin_json})
    scanner = LocalScanner(run_command=runner)
    plugins = scanner.get_plugins()
    assert plugins == ["contact-form-7", "yoast-seo"]


def test_get_database_size_parses_wp_cli_output():
    db_json = json.dumps([{"name": "wp_posts", "size": 52428800}])  # 50 MB total in this fake
    runner = _fake_command_runner({("wp", "db", "size", "--format=json", "--size_format=b"): db_json})
    scanner = LocalScanner(run_command=runner)
    size_mb = scanner.get_database_size_mb()
    assert size_mb == 50.0


def test_get_server_specs_parses_nproc_free_df():
    def runner(args):
        if args[:1] == ["nproc"]:
            return "4\n"
        if args[:1] == ["free"]:
            return "              total        used        free\nMem:           7975        2000        1000\n"
        if args[:1] == ["df"]:
            return "Filesystem  1G-blocks  Used Avail Use% Mounted on\n/dev/sda1       50G   10G   40G  20% /\n"
        raise RuntimeError(f"unexpected command {args}")

    scanner = LocalScanner(run_command=runner)
    specs = scanner.get_server_specs()
    assert specs["cpu_cores"] == 4
    assert specs["ram_mb"] == 7975
    assert specs["disk_gb"] == 50


def test_scan_with_access_log_marks_traffic_measured():
    plugin_json = json.dumps([{"name": "yoast-seo"}])

    def runner(args):
        if args[:3] == ["wp", "plugin", "list"]:
            return plugin_json
        if args[:2] == ["wp", "db"]:
            raise RuntimeError("no db access in this test")
        if args[:1] == ["du"]:
            raise RuntimeError("no filesystem access in this test")
        if args[:1] in (["nproc"], ["free"], ["df"]):
            raise RuntimeError("no server access in this test")
        raise RuntimeError(f"unexpected command {args}")

    def reader(path):
        if "access.log" in path:
            return SAMPLE_ACCESS_LOG
        raise FileNotFoundError(path)

    scanner = LocalScanner(run_command=runner, read_file=reader)
    profile = scanner.scan(access_log_path="access.log", wp_config_path="missing-wp-config.php")

    assert profile.traffic.measured is True
    assert profile.traffic.sessions_per_day > 0
    assert profile.plugin_detection_exhaustive is True


def test_scan_woocommerce_plugin_sets_content_profile():
    plugin_json = json.dumps([{"name": "woocommerce"}])

    def runner(args):
        if args[:3] == ["wp", "plugin", "list"]:
            return plugin_json
        raise RuntimeError("no access in this test")

    def reader(path):
        raise FileNotFoundError(path)

    scanner = LocalScanner(run_command=runner, read_file=reader)
    profile = scanner.scan(access_log_path=None, wp_config_path="missing.php")
    assert profile.content_profile == ContentProfile.WOOCOMMERCE


def test_scan_never_leaks_db_password_even_if_wp_config_is_readable():
    plugin_json = json.dumps([{"name": "yoast-seo"}])
    wp_config_with_secrets = "<?php\ndefine('DB_PASSWORD', 'TopSecret123');\ndefine('WP_CACHE', true);\n"

    def runner(args):
        if args[:3] == ["wp", "plugin", "list"]:
            return plugin_json
        raise RuntimeError("no access in this test")

    def reader(path):
        if "wp-config" in path:
            return wp_config_with_secrets
        raise FileNotFoundError(path)

    scanner = LocalScanner(run_command=runner, read_file=reader)
    profile = scanner.scan(access_log_path=None, wp_config_path="wp-config.php")

    # Nothing in the resulting profile (including its notes) should ever contain the
    # secret value, even though the scanner did read the file containing it.
    profile_repr = repr(profile)
    assert "TopSecret123" not in profile_repr
