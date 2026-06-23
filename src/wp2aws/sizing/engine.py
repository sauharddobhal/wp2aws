"""Maps a SiteProfile to a sizing decision, using the same capacity model documented in
wordpress-high-traffic-aws's README: peak-to-average ratio, then cache-hit-ratio-driven
origin load, then a tier lookup.

The cache-hit-ratio assumption is the single most consequential number here, and it
moves with content profile rather than being a flat constant, since that's the actual
lesson from wordpress-high-traffic-aws: this approach is sized for cacheable content
traffic and degrades hard for logged-in/transactional traffic.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ContentProfile, SiteProfile

# Cache-hit-ratio assumption by content profile. CONTENT matches the 92% figure used in
# wordpress-high-traffic-aws's own capacity planning section. WOOCOMMERCE and
# MEMBERSHIP are lower because cart/account/logged-in pages can't sit behind CloudFront
# the same way; these are reasonable planning assumptions, not measurements, same
# caveat wordpress-high-traffic-aws makes about its own 92% figure.
CACHE_HIT_RATIO_BY_PROFILE = {
    ContentProfile.CONTENT: 0.92,
    ContentProfile.WOOCOMMERCE: 0.55,
    ContentProfile.MEMBERSHIP: 0.25,
}


@dataclass
class SizingDecision:
    tier: str  # "small" | "medium" | "large"
    origin_req_per_sec: float
    cache_hit_ratio_used: float

    instance_type: str
    app_min_size: int
    app_max_size: int
    app_desired_capacity: int

    db_instance_class: str
    db_reader_count: int

    redis_node_type: str
    redis_num_cache_clusters: int

    single_nat_gateway: bool

    reasoning: list[str]


def _tier_for_origin_load(origin_req_per_sec: float) -> str:
    if origin_req_per_sec < 15:
        return "small"
    if origin_req_per_sec < 75:
        return "medium"
    return "large"


_TIER_SPECS = {
    "small": {
        "instance_type": "t4g.medium",
        "app_min_size": 2,
        "app_max_size": 4,
        "app_desired_capacity": 2,
        "db_instance_class": "db.r6g.large",
        "db_reader_count": 1,
        "redis_node_type": "cache.r6g.large",
        "redis_num_cache_clusters": 2,
        "single_nat_gateway": True,
    },
    "medium": {
        "instance_type": "t4g.large",
        "app_min_size": 2,
        "app_max_size": 6,
        "app_desired_capacity": 3,
        "db_instance_class": "db.r6g.large",
        "db_reader_count": 1,
        "redis_node_type": "cache.r6g.large",
        "redis_num_cache_clusters": 2,
        "single_nat_gateway": False,
    },
    "large": {
        "instance_type": "m6g.xlarge",
        "app_min_size": 3,
        "app_max_size": 10,
        "app_desired_capacity": 4,
        "db_instance_class": "db.r6g.xlarge",
        "db_reader_count": 2,
        "redis_node_type": "cache.r6g.xlarge",
        "redis_num_cache_clusters": 3,
        "single_nat_gateway": False,
    },
}


def compute_sizing(profile: SiteProfile) -> SizingDecision:
    reasoning: list[str] = []

    average_req_per_sec = profile.traffic.sessions_per_day / 86400
    peak_req_per_sec = average_req_per_sec * profile.traffic.peak_to_average_ratio
    reasoning.append(
        f"{profile.traffic.sessions_per_day:,} sessions/day -> "
        f"{average_req_per_sec:.1f} req/s average, "
        f"{peak_req_per_sec:.1f} req/s peak at "
        f"{profile.traffic.peak_to_average_ratio}x "
        f"({'measured' if profile.traffic.measured else 'assumed'} peak ratio)"
    )

    cache_hit_ratio = CACHE_HIT_RATIO_BY_PROFILE[profile.content_profile]
    reasoning.append(
        f"Content profile '{profile.content_profile.value}' assumes a "
        f"{cache_hit_ratio:.0%} CDN cache-hit ratio"
    )

    origin_req_per_sec = peak_req_per_sec * (1 - cache_hit_ratio)
    reasoning.append(f"Origin load at peak: {origin_req_per_sec:.1f} req/s")

    tier = _tier_for_origin_load(origin_req_per_sec)
    reasoning.append(f"Origin load of {origin_req_per_sec:.1f} req/s maps to tier '{tier}'")

    if profile.database_size_mb and profile.database_size_mb > 20_000:
        reasoning.append(
            f"Database size ({profile.database_size_mb:,.0f} MB) is large; consider "
            f"the next tier up's db_instance_class even if origin load alone "
            f"suggested '{tier}'"
        )

    spec = _TIER_SPECS[tier]

    return SizingDecision(
        tier=tier,
        origin_req_per_sec=origin_req_per_sec,
        cache_hit_ratio_used=cache_hit_ratio,
        reasoning=reasoning,
        **spec,
    )
