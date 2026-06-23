import pytest

from wp2aws.models import ContentProfile, ScanMode, SiteProfile, TrafficProfile
from wp2aws.sizing.cost import estimate_cost
from wp2aws.sizing.engine import compute_sizing


def _profile(sessions_per_day, **kwargs):
    return SiteProfile(
        source_url="https://example.com",
        scan_mode=ScanMode.REMOTE,
        traffic=TrafficProfile(sessions_per_day=sessions_per_day),
        **kwargs,
    )


def test_estimate_cost_produces_positive_total():
    profile = _profile(sessions_per_day=500_000)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    assert estimate.total_monthly_usd > 0


def test_estimate_cost_uses_bundled_snapshot_by_default():
    profile = _profile(sessions_per_day=500_000)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    assert "bundled snapshot" in estimate.pricing_source


def test_higher_traffic_costs_more():
    low_profile = _profile(sessions_per_day=50_000)
    low_decision = compute_sizing(low_profile)
    low_estimate = estimate_cost(low_decision, low_profile)

    high_profile = _profile(sessions_per_day=20_000_000)
    high_decision = compute_sizing(high_profile)
    high_estimate = estimate_cost(high_decision, high_profile)

    assert high_estimate.total_monthly_usd > low_estimate.total_monthly_usd


def test_measured_database_size_changes_basis_text():
    profile = _profile(sessions_per_day=500_000, database_size_mb=51200)  # 50 GB
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    db_storage_item = next(item for item in estimate.line_items if item.name == "Aurora storage")
    assert "measured" in db_storage_item.basis
    assert "50.0 GB" in db_storage_item.basis


def test_unmeasured_database_size_uses_default_and_says_so():
    profile = _profile(sessions_per_day=500_000)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    db_storage_item = next(item for item in estimate.line_items if item.name == "Aurora storage")
    assert "default estimate" in db_storage_item.basis
    assert "not measured" in db_storage_item.basis


def test_all_line_items_have_nonneg_cost_and_basis_text():
    profile = _profile(sessions_per_day=5_000_000, content_profile=ContentProfile.WOOCOMMERCE)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    for item in estimate.line_items:
        assert item.monthly_usd >= 0
        assert len(item.basis) > 0


def test_total_equals_sum_of_line_items():
    profile = _profile(sessions_per_day=1_000_000)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    assert estimate.total_monthly_usd == round(
        sum(item.monthly_usd for item in estimate.line_items), 2
    )


def test_tiered_cloudfront_pricing_cheaper_per_gb_at_high_volume_than_flat_rate():
    from wp2aws.sizing.cost import _tiered_cloudfront_cost, _load_bundled_pricing

    tiers = _load_bundled_pricing()["cloudfront_tiered_pricing_usd_per_gb"]

    small_volume_gb = 1024  # 1 TB, well within the first tier
    large_volume_gb = 300 * 1024  # 300 TB, spans multiple discount tiers

    small_cost = _tiered_cloudfront_cost(small_volume_gb, tiers)
    large_cost = _tiered_cloudfront_cost(large_volume_gb, tiers)

    small_effective_rate = small_cost / small_volume_gb
    large_effective_rate = large_cost / large_volume_gb

    # The blended effective rate at high volume must be lower than at low volume,
    # since later tiers are cheaper per GB. A flat-rate model would show these as equal.
    assert large_effective_rate < small_effective_rate


def test_tiered_cloudfront_pricing_matches_flat_rate_within_first_tier():
    from wp2aws.sizing.cost import _tiered_cloudfront_cost, _load_bundled_pricing

    tiers = _load_bundled_pricing()["cloudfront_tiered_pricing_usd_per_gb"]
    first_tier_rate = tiers[0]["rate"]

    volume_gb = 500  # well within the first 10 TB tier
    cost = _tiered_cloudfront_cost(volume_gb, tiers)
    assert cost == pytest.approx(volume_gb * first_tier_rate, rel=1e-6)


def test_high_traffic_cloudfront_cost_is_meaningfully_lower_than_naive_flat_rate():
    # Regression guard for the bug this was built to fix: a flat per-GB rate applied to
    # very high volume overestimates cost since it ignores AWS's real volume discounts.
    # Compare the tiered result against what a flat rate (using the first tier's price)
    # would have produced for the same volume, rather than asserting an absolute number
    # that would be fragile to the exact tier boundaries chosen.
    from wp2aws.sizing.cost import _load_bundled_pricing, _tiered_cloudfront_cost

    profile = _profile(sessions_per_day=5_000_000)
    decision = compute_sizing(profile)
    estimate = estimate_cost(decision, profile)
    cdn_item = next(item for item in estimate.line_items if item.name == "CloudFront data transfer")

    tiers = _load_bundled_pricing()["cloudfront_tiered_pricing_usd_per_gb"]
    first_tier_rate = tiers[0]["rate"]

    monthly_page_views = profile.traffic.sessions_per_day * 30
    estimated_cdn_gb = (monthly_page_views * 2.0) / 1024
    cache_hit_ratio = decision.cache_hit_ratio_used
    billable_gb = estimated_cdn_gb * (1 - cache_hit_ratio * 0.5)
    naive_flat_rate_cost = billable_gb * first_tier_rate

    assert cdn_item.monthly_usd < naive_flat_rate_cost
