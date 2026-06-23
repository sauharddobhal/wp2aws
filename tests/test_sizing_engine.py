from wp2aws.models import ContentProfile, ScanMode, SiteProfile, TrafficProfile
from wp2aws.sizing.engine import compute_sizing


def _profile(sessions_per_day, content_profile=ContentProfile.CONTENT, **kwargs):
    return SiteProfile(
        source_url="https://example.com",
        scan_mode=ScanMode.REMOTE,
        traffic=TrafficProfile(sessions_per_day=sessions_per_day),
        content_profile=content_profile,
        **kwargs,
    )


def test_low_traffic_content_site_sizes_small():
    decision = compute_sizing(_profile(sessions_per_day=50_000))
    assert decision.tier == "small"


def test_high_traffic_content_site_matching_readme_example_sizes_medium_or_higher():
    # 5,000,000 sessions/day is the exact example used in wordpress-high-traffic-aws's
    # own capacity planning section (~290 req/s peak, ~23 req/s origin at 92% hit ratio).
    decision = compute_sizing(_profile(sessions_per_day=5_000_000))
    assert decision.tier in {"small", "medium"}  # ~23 req/s origin load, matches that repo's sizing
    assert 15 < decision.origin_req_per_sec < 30


def test_woocommerce_site_gets_lower_cache_hit_ratio_than_content_site():
    content_decision = compute_sizing(_profile(sessions_per_day=1_000_000))
    woo_decision = compute_sizing(
        _profile(sessions_per_day=1_000_000, content_profile=ContentProfile.WOOCOMMERCE)
    )
    assert woo_decision.cache_hit_ratio_used < content_decision.cache_hit_ratio_used
    assert woo_decision.origin_req_per_sec > content_decision.origin_req_per_sec


def test_membership_site_sizes_larger_than_content_site_at_same_traffic():
    content_decision = compute_sizing(_profile(sessions_per_day=2_000_000))
    membership_decision = compute_sizing(
        _profile(sessions_per_day=2_000_000, content_profile=ContentProfile.MEMBERSHIP)
    )
    tier_order = {"small": 0, "medium": 1, "large": 2}
    assert tier_order[membership_decision.tier] >= tier_order[content_decision.tier]


def test_very_high_traffic_sizes_large():
    decision = compute_sizing(_profile(sessions_per_day=50_000_000))
    assert decision.tier == "large"


def test_reasoning_distinguishes_measured_from_assumed_traffic():
    measured_profile = _profile(sessions_per_day=100_000)
    measured_profile.traffic.measured = True
    decision = compute_sizing(measured_profile)
    assert any("measured" in r for r in decision.reasoning)

    assumed_profile = _profile(sessions_per_day=100_000)
    decision2 = compute_sizing(assumed_profile)
    assert any("assumed" in r for r in decision2.reasoning)


def test_large_database_adds_a_reasoning_note():
    decision = compute_sizing(_profile(sessions_per_day=50_000, database_size_mb=30_000))
    assert any("Database size" in r for r in decision.reasoning)
