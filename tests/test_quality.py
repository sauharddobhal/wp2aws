from wp2aws.models import ScanMode, SiteProfile, TrafficProfile
from wp2aws.sizing.quality import score_data_quality


def _bare_profile(**overrides):
    base = dict(
        source_url="https://example.com",
        scan_mode=ScanMode.REMOTE,
        traffic=TrafficProfile(sessions_per_day=100_000, measured=False),
    )
    base.update(overrides)
    return SiteProfile(**base)


def test_fully_unmeasured_profile_scores_zero():
    profile = _bare_profile()
    score = score_data_quality(profile)
    assert score.measured_count == 0
    assert score.total_count == 6


def test_fully_measured_profile_scores_max():
    profile = _bare_profile(
        traffic=TrafficProfile(sessions_per_day=100_000, measured=True),
        plugin_detection_exhaustive=True,
        database_size_mb=500.0,
        media_library_size_mb=1000.0,
        measured_avg_page_weight_mb=2.5,
        server_cpu_cores=4,
    )
    score = score_data_quality(profile)
    assert score.measured_count == score.total_count == 6
    assert score.fraction == 1.0


def test_partial_measurement_lists_correct_fields():
    profile = _bare_profile(database_size_mb=500.0, server_cpu_cores=2)
    score = score_data_quality(profile)
    assert score.measured_count == 2
    assert "database_size" in score.measured_fields
    assert "server_specs" in score.measured_fields
    assert "traffic" in score.assumed_fields
    assert "page_weight" in score.assumed_fields


def test_fraction_is_zero_safe():
    profile = _bare_profile()
    score = score_data_quality(profile)
    assert 0.0 <= score.fraction <= 1.0
