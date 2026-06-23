"""Renders the scan + sizing + cost results as readable text, and optionally as a
Markdown report file.
"""

from __future__ import annotations

from .models import SiteProfile
from .sizing.cost import CostEstimate
from .sizing.engine import SizingDecision
from .sizing.quality import score_data_quality


def render_text_report(
    profile: SiteProfile,
    decision: SizingDecision,
    cost: CostEstimate,
    current_hosting_cost_usd: float | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"wp2aws scan report ({profile.scan_mode.value} mode)")
    if profile.source_url:
        lines.append(f"Site: {profile.source_url}")

    quality = score_data_quality(profile)
    lines.append(
        f"Data quality: {quality.measured_count}/{quality.total_count} inputs measured "
        f"({', '.join(quality.measured_fields) or 'none'}); rest are defaults/assumptions "
        f"({', '.join(quality.assumed_fields) or 'none'})"
    )
    lines.append("")

    lines.append("Site profile")
    lines.append(f"  Content profile: {profile.content_profile.value}")
    if profile.post_count is not None:
        lines.append(f"  Posts: {profile.post_count}")
    if profile.page_count is not None:
        lines.append(f"  Pages: {profile.page_count}")
    plugin_label = "exhaustive" if profile.plugin_detection_exhaustive else "asset-detected, not exhaustive"
    lines.append(f"  Plugins detected ({plugin_label}): {', '.join(profile.plugins) or 'none detected'}")
    if profile.database_size_mb is not None:
        lines.append(f"  Database size: {profile.database_size_mb:,.1f} MB")
    if profile.media_library_size_mb is not None:
        lines.append(f"  Media library size: {profile.media_library_size_mb:,.1f} MB")
    if profile.server_cpu_cores is not None:
        lines.append(
            f"  Server: {profile.server_cpu_cores} cores, "
            f"{profile.server_ram_mb or '?'} MB RAM, {profile.server_disk_gb or '?'} GB disk"
        )
    lines.append(
        f"  Traffic: {profile.traffic.sessions_per_day:,} sessions/day "
        f"({'measured from access logs' if profile.traffic.measured else 'user-provided estimate'})"
    )
    lines.append("")

    lines.append("Sizing decision")
    for reason in decision.reasoning:
        lines.append(f"  - {reason}")
    lines.append(f"  Tier: {decision.tier}")
    lines.append(
        f"  App tier: {decision.app_desired_capacity}x {decision.instance_type} "
        f"(min {decision.app_min_size}, max {decision.app_max_size})"
    )
    lines.append(f"  Database: {decision.db_instance_class}, {decision.db_reader_count} reader(s)")
    lines.append(
        f"  Cache: {decision.redis_num_cache_clusters}x {decision.redis_node_type}"
    )
    lines.append(f"  NAT strategy: {'single shared gateway' if decision.single_nat_gateway else 'one per AZ'}")
    lines.append("")

    lines.append(f"Cost estimate (source: {cost.pricing_source})")
    for item in cost.line_items:
        lines.append(f"  {item.name:<40} ${item.monthly_usd:>9,.2f}/mo   ({item.basis})")
    lines.append(f"  {'TOTAL':<40} ${cost.total_monthly_usd:>9,.2f}/mo")

    if current_hosting_cost_usd is not None:
        delta = cost.total_monthly_usd - current_hosting_cost_usd
        lines.append("")
        lines.append("Hosting cost comparison")
        lines.append(f"  Current hosting:  ${current_hosting_cost_usd:>9,.2f}/mo")
        lines.append(f"  AWS estimate:     ${cost.total_monthly_usd:>9,.2f}/mo")
        if delta > 0:
            pct = (delta / current_hosting_cost_usd * 100) if current_hosting_cost_usd else 0
            lines.append(f"  Difference:       ${delta:>9,.2f}/mo MORE than current ({pct:.0f}% increase)")
        elif delta < 0:
            pct = (-delta / current_hosting_cost_usd * 100) if current_hosting_cost_usd else 0
            lines.append(f"  Difference:       ${-delta:>9,.2f}/mo LESS than current ({pct:.0f}% savings)")
        else:
            lines.append("  Difference:       roughly the same")
        lines.append(
            "  Note: this compares sticker price only. It does not account for "
            "engineering time to migrate and maintain, or for capability you gain "
            "(autoscaling, managed failover) that your current hosting may not offer."
        )

    lines.append("")

    if profile.notes:
        lines.append("Notes")
        for note in profile.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def render_markdown_report(
    profile: SiteProfile,
    decision: SizingDecision,
    cost: CostEstimate,
    current_hosting_cost_usd: float | None = None,
) -> str:
    text = render_text_report(profile, decision, cost, current_hosting_cost_usd)
    # Reuse the same content inside a fenced code block rather than maintaining two
    # separate renderers; good enough for a generated artifact meant to be read once
    # alongside the tfvars file, not a polished long-lived document.
    return f"# wp2aws scan report\n\n```\n{text}\n```\n"
