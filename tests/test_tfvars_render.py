import re
from pathlib import Path

from wp2aws.models import ContentProfile, ScanMode, SiteProfile, TrafficProfile
from wp2aws.sizing.engine import compute_sizing
from wp2aws.sizing.tfvars import render_tfvars

# Points at the sibling repo built earlier in this portfolio. If that repo isn't present
# (e.g. this project is checked out standalone without it alongside), the cross-repo
# validation test is skipped rather than failing, but every other tfvars test still runs.
WORDPRESS_REPO_VARS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "wordpress-high-traffic-aws"
    / "terraform"
    / "environments"
    / "example"
    / "variables.tf"
)


def _profile(sessions_per_day=500_000, **kwargs):
    return SiteProfile(
        source_url="https://example.com",
        scan_mode=ScanMode.REMOTE,
        traffic=TrafficProfile(sessions_per_day=sessions_per_day),
        **kwargs,
    )


def test_render_tfvars_produces_valid_looking_hcl_assignments():
    profile = _profile()
    decision = compute_sizing(profile)
    output = render_tfvars(decision, profile)
    assert 'aws_region = "us-east-1"' in output
    assert "app_min_size" in output
    assert "REPLACE_ME" in output  # placeholders for deployment-specific values


def test_render_tfvars_reflects_sizing_decision_values():
    profile = _profile(sessions_per_day=50_000_000, content_profile=ContentProfile.MEMBERSHIP)
    decision = compute_sizing(profile)
    output = render_tfvars(decision, profile)
    assert decision.instance_type in output
    assert decision.db_instance_class in output
    assert decision.redis_node_type in output


def test_every_emitted_variable_name_is_declared_in_the_real_repo():
    if not WORDPRESS_REPO_VARS_PATH.exists():
        import pytest

        pytest.skip("wordpress-high-traffic-aws repo not present alongside this one")

    profile = _profile()
    decision = compute_sizing(profile)
    output = render_tfvars(decision, profile)

    emitted_var_names = set(re.findall(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=", output, re.MULTILINE))

    declared_vars_text = WORDPRESS_REPO_VARS_PATH.read_text(encoding="utf-8")
    declared_var_names = set(re.findall(r'variable\s+"([a-zA-Z_][a-zA-Z0-9_]*)"', declared_vars_text))

    unknown_vars = emitted_var_names - declared_var_names
    assert not unknown_vars, (
        f"wp2aws emits variables not declared in wordpress-high-traffic-aws: {unknown_vars}"
    )
