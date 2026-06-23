"""Local scanner: run directly on the WordPress server (e.g. over SSH) for measured,
not assumed, traffic and an exhaustive plugin/theme inventory.

Every external call here (subprocess, file reads) is injectable via constructor
parameters specifically so tests don't need a real server, real WP-CLI install, or
real log files.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models import ContentProfile, ScanMode, SiteProfile, TrafficProfile
from .secrets_filter import assert_no_secrets_leaked, extract_safe_constants

# Combined log format: IP - - [timestamp] "METHOD path HTTP/1.1" status size "referrer" "user-agent"
_LOG_LINE_PATTERN = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+) \S+" (?P<status>\d+) (?P<size>\S+) '
    r'"(?P<referrer>[^"]*)" "(?P<user_agent>[^"]*)"'
)

_BOT_USER_AGENT_MARKERS = (
    "bot", "spider", "crawl", "slurp", "facebookexternalhit", "bingpreview",
)

_WOOCOMMERCE_SLUGS = {"woocommerce"}
_MEMBERSHIP_SLUGS = {"memberpress", "restrict-content-pro", "paid-memberships-pro", "wp-members"}

CommandRunner = Callable[[list[str]], str]


@dataclass
class AccessLogStats:
    total_requests: int
    requests_per_day_estimate: float
    peak_hour_to_average_ratio: float
    human_request_fraction: float


def _default_command_runner(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=30).stdout


def parse_access_log(log_text: str) -> AccessLogStats:
    """Parses combined-format access log text into traffic statistics.

    Bot filtering is a simple user-agent substring heuristic, not a robust bot-detection
    system; it under-counts sophisticated bots that spoof browser user-agents and
    over-counts nothing, so human_request_fraction is a conservative (upper-bound-ish)
    estimate of real human traffic, not a precise one.
    """
    hourly_counts: dict[str, int] = {}
    total = 0
    human_total = 0

    for line in log_text.splitlines():
        match = _LOG_LINE_PATTERN.match(line)
        if not match:
            continue
        total += 1
        # timestamp format: "01/Jun/2026:08:00:01 +0000"; bucket by date+hour, not by
        # date alone, splitting once on ":" only separates date from the rest.
        timestamp_parts = match.group("timestamp").split(":")
        hour_key = f"{timestamp_parts[0]}:{timestamp_parts[1]}"
        hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1

        user_agent = match.group("user_agent").lower()
        if not any(marker in user_agent for marker in _BOT_USER_AGENT_MARKERS):
            human_total += 1

    if total == 0 or not hourly_counts:
        return AccessLogStats(0, 0.0, 0.0, 0.0)

    num_hours = len(hourly_counts)
    average_per_hour = total / num_hours
    peak_per_hour = max(hourly_counts.values())
    peak_ratio = (peak_per_hour / average_per_hour) if average_per_hour > 0 else 0.0

    # Extrapolate to a daily figure from however many hours of log we actually have.
    requests_per_day_estimate = average_per_hour * 24

    return AccessLogStats(
        total_requests=total,
        requests_per_day_estimate=requests_per_day_estimate,
        peak_hour_to_average_ratio=round(peak_ratio, 2),
        human_request_fraction=round(human_total / total, 3),
    )


class LocalScanner:
    def __init__(
        self,
        run_command: CommandRunner | None = None,
        read_file: Callable[[str], str] | None = None,
    ):
        self._run_command = run_command or _default_command_runner
        self._read_file = read_file or (lambda path: Path(path).read_text(encoding="utf-8"))

    def _wp_cli(self, *args: str) -> str:
        return self._run_command(["wp", *args, "--allow-root"])

    def get_plugins(self) -> list[str]:
        import json

        output = self._wp_cli("plugin", "list", "--format=json")
        plugins = json.loads(output)
        return sorted(p["name"] for p in plugins)

    def get_database_size_mb(self) -> float | None:
        import json

        try:
            output = self._wp_cli("db", "size", "--format=json", "--size_format=b")
        except Exception:
            return None
        data = json.loads(output)
        size_bytes = data[0]["size"] if isinstance(data, list) else data.get("size")
        return round(int(size_bytes) / (1024 * 1024), 1) if size_bytes else None

    def get_media_library_size_mb(self, uploads_path: str = "wp-content/uploads") -> float | None:
        try:
            output = self._run_command(["du", "-sb", uploads_path])
        except Exception:
            return None
        size_bytes_str = output.split()[0]
        return round(int(size_bytes_str) / (1024 * 1024), 1)

    def get_server_specs(self) -> dict:
        specs: dict = {}
        try:
            specs["cpu_cores"] = int(self._run_command(["nproc"]).strip())
        except Exception:
            specs["cpu_cores"] = None
        try:
            mem_output = self._run_command(["free", "-m"])
            # Second line, second column is total memory in MB in `free -m` output.
            second_line = mem_output.splitlines()[1]
            specs["ram_mb"] = int(second_line.split()[1])
        except Exception:
            specs["ram_mb"] = None
        try:
            df_output = self._run_command(["df", "-BG", "/"])
            second_line = df_output.splitlines()[1]
            specs["disk_gb"] = int(second_line.split()[1].rstrip("G"))
        except Exception:
            specs["disk_gb"] = None
        return specs

    def get_safe_wp_config_constants(self, wp_config_path: str = "wp-config.php") -> dict[str, str]:
        php_source = self._read_file(wp_config_path)
        extracted = extract_safe_constants(php_source)
        assert_no_secrets_leaked(extracted)  # defense in depth, see secrets_filter.py
        return extracted

    def scan(
        self,
        access_log_path: str | None = None,
        wp_config_path: str = "wp-config.php",
        uploads_path: str = "wp-content/uploads",
        peak_to_average_ratio_default: float = 5.0,
    ) -> SiteProfile:
        notes: list[str] = []

        plugins: list[str] = []
        try:
            plugins = self.get_plugins()
        except Exception as exc:
            notes.append(f"Could not retrieve plugin list via WP-CLI: {exc}")

        content_profile = self._infer_content_profile(plugins)

        database_size_mb = self.get_database_size_mb()
        media_library_size_mb = self.get_media_library_size_mb(uploads_path)
        server_specs = self.get_server_specs()

        try:
            self.get_safe_wp_config_constants(wp_config_path)
        except Exception as exc:
            notes.append(f"Could not read wp-config.php: {exc}")

        if access_log_path:
            log_text = self._read_file(access_log_path)
            stats = parse_access_log(log_text)
            traffic = TrafficProfile(
                sessions_per_day=int(stats.requests_per_day_estimate * stats.human_request_fraction),
                peak_to_average_ratio=stats.peak_hour_to_average_ratio or peak_to_average_ratio_default,
                measured=True,
            )
            notes.append(
                f"Traffic measured from access log: {stats.total_requests} requests parsed, "
                f"{stats.human_request_fraction:.0%} estimated human (bot-filtered by user-agent "
                f"heuristic, not a robust bot-detection system)"
            )
        else:
            traffic = TrafficProfile(sessions_per_day=0, measured=False)
            notes.append("No access log provided; traffic is unset. Pass --access-log for a measured figure.")

        return SiteProfile(
            source_url=None,
            scan_mode=ScanMode.LOCAL,
            traffic=traffic,
            content_profile=content_profile,
            plugins=plugins,
            plugin_detection_exhaustive=bool(plugins),
            database_size_mb=database_size_mb,
            media_library_size_mb=media_library_size_mb,
            server_cpu_cores=server_specs.get("cpu_cores"),
            server_ram_mb=server_specs.get("ram_mb"),
            server_disk_gb=server_specs.get("disk_gb"),
            notes=notes,
        )

    def _infer_content_profile(self, plugins: list[str]) -> ContentProfile:
        lowered = {p.lower() for p in plugins}
        if lowered & _WOOCOMMERCE_SLUGS:
            return ContentProfile.WOOCOMMERCE
        if lowered & _MEMBERSHIP_SLUGS:
            return ContentProfile.MEMBERSHIP
        return ContentProfile.CONTENT
