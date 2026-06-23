from wp2aws.models import ScanMode, SiteProfile, TrafficProfile
from wp2aws.report import render_markdown_report, render_text_report
from wp2aws.sizing.cost import estimate_cost
from wp2aws.sizing.engine import compute_sizing


def _profile(sessions_per_day=500_000, **kwargs):
    return SiteProfile(
        source_url="https://example.com",
        scan_mode=ScanMode.REMOTE,
        traffic=TrafficProfile(sessions_per_day=sessions_per_day),
        **kwargs,
    )


def test_report_includes_data_quality_line():
    profile = _profile()
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile)
    report = render_text_report(profile, decision, cost)
    assert "Data quality:" in report
    assert "/6 inputs measured" in report


def test_report_without_hosting_cost_omits_comparison_section():
    profile = _profile()
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile)
    report = render_text_report(profile, decision, cost)
    assert "Hosting cost comparison" not in report


def test_report_with_hosting_cost_shows_increase_when_aws_costs_more():
    profile = _profile()
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile)
    report = render_text_report(profile, decision, cost, current_hosting_cost_usd=1.0)
    assert "Hosting cost comparison" in report
    assert "MORE than current" in report


def test_report_with_hosting_cost_shows_savings_when_aws_costs_less():
    profile = _profile(sessions_per_day=1_000)  # tiny traffic, low AWS estimate
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile)
    report = render_text_report(profile, decision, cost, current_hosting_cost_usd=999_999.0)
    assert "LESS than current" in report
    assert "savings" in report


def test_markdown_report_propagates_hosting_cost_comparison():
    profile = _profile()
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile)
    markdown = render_markdown_report(profile, decision, cost, current_hosting_cost_usd=50.0)
    assert "Hosting cost comparison" in markdown
