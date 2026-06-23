"""Shared data models. Both scanners (remote, local) populate a SiteProfile; fields
either scanner can't determine stay None rather than being guessed, so the sizing
engine always knows what's measured versus assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScanMode(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"
    DEMO = "demo"


class ContentProfile(str, Enum):
    """How cacheable the site's traffic is, which drives the cache-hit-ratio
    assumption fed into the sizing engine. Mirrors the distinction
    wordpress-high-traffic-aws's README makes explicit: this whole approach is sized
    for content/blog-style traffic, and degrades for logged-in/transactional traffic.
    """

    CONTENT = "content"  # blog/news/marketing, mostly anonymous, highly cacheable
    WOOCOMMERCE = "woocommerce"  # cart/checkout/account pages, much less cacheable
    MEMBERSHIP = "membership"  # mostly logged-in traffic, least cacheable


@dataclass
class TrafficProfile:
    sessions_per_day: int
    peak_to_average_ratio: float = 5.0
    measured: bool = False  # True only when derived from real access logs (local mode)


@dataclass
class SiteProfile:
    source_url: str | None
    scan_mode: ScanMode

    traffic: TrafficProfile

    content_profile: ContentProfile = ContentProfile.CONTENT
    plugins: list[str] = field(default_factory=list)
    plugin_detection_exhaustive: bool = False  # True only for local/WP-CLI detection

    post_count: int | None = None
    page_count: int | None = None

    database_size_mb: float | None = None
    media_library_size_mb: float | None = None
    measured_avg_page_weight_mb: float | None = None

    existing_cache_headers_present: bool = False

    # Local-mode-only server facts
    server_cpu_cores: int | None = None
    server_ram_mb: int | None = None
    server_disk_gb: int | None = None
    php_version: str | None = None
    php_memory_limit: str | None = None

    notes: list[str] = field(default_factory=list)
