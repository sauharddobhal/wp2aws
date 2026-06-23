"""Scores how much of a SiteProfile is real measurement versus default/assumption.

This exists to make the tool's core honesty claim ("we tell you what's measured versus
assumed") visible as a single glanceable number at the top of the report, rather than
something a reader only discovers by reading every line item's basis text.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import SiteProfile


@dataclass
class DataQualityScore:
    measured_count: int
    total_count: int
    measured_fields: list[str]
    assumed_fields: list[str]

    @property
    def fraction(self) -> float:
        return self.measured_count / self.total_count if self.total_count else 0.0


def score_data_quality(profile: SiteProfile) -> DataQualityScore:
    checks = {
        "traffic": profile.traffic.measured,
        "plugin_list": profile.plugin_detection_exhaustive,
        "database_size": profile.database_size_mb is not None,
        "media_library_size": profile.media_library_size_mb is not None,
        "page_weight": profile.measured_avg_page_weight_mb is not None,
        "server_specs": profile.server_cpu_cores is not None,
    }

    measured_fields = [name for name, is_measured in checks.items() if is_measured]
    assumed_fields = [name for name, is_measured in checks.items() if not is_measured]

    return DataQualityScore(
        measured_count=len(measured_fields),
        total_count=len(checks),
        measured_fields=measured_fields,
        assumed_fields=assumed_fields,
    )
