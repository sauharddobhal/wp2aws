"""Monthly AWS cost estimate from a SizingDecision.

Default mode reads the bundled, dated pricing snapshot in data/pricing_snapshot.json so
this works completely offline. --live-pricing instead fetches current public pricing
from AWS's Price List Bulk API (no AWS credentials required for that endpoint, just
outbound internet access).

Every line item carries a short basis string explaining where its number came from, so
a report reader can see which figures are real measurements, which are reasonable
defaults, and which are AWS list prices that will drift over time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..models import SiteProfile
from .engine import SizingDecision

PRICING_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "pricing_snapshot.json"

# Used when the site profile doesn't tell us database/media size; clearly flagged as a
# default in the resulting line item, not presented as a measurement.
DEFAULT_DB_STORAGE_GB = 20
DEFAULT_MEDIA_LIBRARY_GB = 10
DEFAULT_AVG_PAGE_WEIGHT_MB = 2.0
DEFAULT_NAT_DATA_TRANSFER_GB = 50


@dataclass
class CostLineItem:
    name: str
    monthly_usd: float
    basis: str


@dataclass
class CostEstimate:
    line_items: list[CostLineItem]
    total_monthly_usd: float
    pricing_source: str  # "bundled snapshot (<date>)" or "live AWS pricing API"


def _load_bundled_pricing() -> dict:
    return json.loads(PRICING_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def fetch_live_pricing() -> dict:
    """Fetches current pricing from AWS's public Bulk Pricing API and reshapes it into
    the same structure as the bundled snapshot.

    This function requires outbound internet access to pricing.us-east-1.amazonaws.com
    and is not exercised by this project's offline test suite for that reason; the
    bundled-snapshot path above is what's covered by automated tests. Treat this as a
    working starting point and verify it end-to-end in an environment with internet
    access before relying on it.
    """
    import requests

    # AWS publishes per-service pricing index files; this fetches the EC2 index as a
    # representative example and falls back to the bundled snapshot for anything this
    # function doesn't map, rather than silently returning incomplete data.
    response = requests.get(
        "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.json",
        timeout=15,
    )
    response.raise_for_status()
    raw = response.json()

    pricing = _load_bundled_pricing()
    pricing["region"] = "us-east-1"
    pricing["snapshot_date"] = "live"
    pricing["disclaimer"] = (
        "Live pricing fetched from AWS's public Bulk Pricing API for EC2; other "
        "services in this estimate still use the bundled snapshot values, since fully "
        "mapping every service's pricing index is out of scope for this tool."
    )

    products = raw.get("products", {})
    on_demand_terms = raw.get("terms", {}).get("OnDemand", {})
    for sku, product in products.items():
        attrs = product.get("attributes", {})
        instance_type = attrs.get("instanceType")
        if (
            instance_type in pricing["ec2_hourly_usd"]
            and attrs.get("tenancy") == "Shared"
            and attrs.get("operatingSystem") == "Linux"
            and attrs.get("preInstalledSw") == "NA"
            and attrs.get("capacitystatus") == "Used"
        ):
            sku_terms = on_demand_terms.get(sku, {})
            for term in sku_terms.values():
                for dim in term.get("priceDimensions", {}).values():
                    price = float(dim.get("pricePerUnit", {}).get("USD", 0) or 0)
                    if price > 0:
                        pricing["ec2_hourly_usd"][instance_type] = price

    return pricing


def estimate_cost(
    decision: SizingDecision, profile: SiteProfile, use_live_pricing: bool = False
) -> CostEstimate:
    if use_live_pricing:
        pricing = fetch_live_pricing()
        source = "live AWS pricing API (EC2 only; other services from bundled snapshot)"
    else:
        pricing = _load_bundled_pricing()
        source = f"bundled snapshot ({pricing['snapshot_date']})"

    hours = pricing["hours_per_month"]
    items: list[CostLineItem] = []

    # --- Compute ---
    ec2_rate = pricing["ec2_hourly_usd"][decision.instance_type]
    ec2_monthly = ec2_rate * hours * decision.app_desired_capacity
    items.append(
        CostLineItem(
            name=f"EC2 ({decision.app_desired_capacity}x {decision.instance_type})",
            monthly_usd=round(ec2_monthly, 2),
            basis="desired capacity from sizing decision; actual cost varies with autoscaling",
        )
    )

    # --- Database ---
    aurora_instance_rate = pricing["aurora_instance_hourly_usd"][decision.db_instance_class]
    aurora_instance_count = 1 + decision.db_reader_count  # writer + readers
    aurora_compute_monthly = aurora_instance_rate * hours * aurora_instance_count
    db_storage_gb = (
        profile.database_size_mb / 1024 if profile.database_size_mb else DEFAULT_DB_STORAGE_GB
    )
    aurora_storage_monthly = pricing["aurora_storage_per_gb_month_usd"] * db_storage_gb
    items.append(
        CostLineItem(
            name=f"Aurora ({aurora_instance_count}x {decision.db_instance_class})",
            monthly_usd=round(aurora_compute_monthly, 2),
            basis="1 writer + db_reader_count readers",
        )
    )
    items.append(
        CostLineItem(
            name="Aurora storage",
            monthly_usd=round(aurora_storage_monthly, 2),
            basis=(
                f"measured database size ({db_storage_gb:.1f} GB)"
                if profile.database_size_mb
                else f"default estimate ({DEFAULT_DB_STORAGE_GB} GB, not measured)"
            ),
        )
    )

    # --- Cache ---
    redis_rate = pricing["elasticache_hourly_usd"][decision.redis_node_type]
    redis_monthly = redis_rate * hours * decision.redis_num_cache_clusters
    items.append(
        CostLineItem(
            name=f"ElastiCache ({decision.redis_num_cache_clusters}x {decision.redis_node_type})",
            monthly_usd=round(redis_monthly, 2),
            basis="from sizing decision",
        )
    )

    # --- Networking ---
    nat_count = 1 if decision.single_nat_gateway else 3
    nat_monthly = (
        pricing["nat_gateway_hourly_usd"] * hours * nat_count
        + pricing["nat_gateway_per_gb_usd"] * DEFAULT_NAT_DATA_TRANSFER_GB
    )
    items.append(
        CostLineItem(
            name=f"NAT Gateway ({nat_count}x)",
            monthly_usd=round(nat_monthly, 2),
            basis=f"data transfer assumed at {DEFAULT_NAT_DATA_TRANSFER_GB} GB/month (not measured)",
        )
    )

    average_req_per_sec = profile.traffic.sessions_per_day / 86400
    estimated_lcu = max(average_req_per_sec / 25, 1.0)  # rough rule of thumb, not exact
    alb_monthly = (
        pricing["alb_hourly_usd"] * hours + pricing["alb_per_lcu_hour_usd"] * hours * estimated_lcu
    )
    items.append(
        CostLineItem(
            name="Application Load Balancer",
            monthly_usd=round(alb_monthly, 2),
            basis="LCU estimated from average request rate; rough rule of thumb, not exact",
        )
    )

    # --- Storage & CDN ---
    media_gb = (
        profile.media_library_size_mb / 1024
        if profile.media_library_size_mb
        else DEFAULT_MEDIA_LIBRARY_GB
    )
    s3_monthly = pricing["s3_standard_per_gb_month_usd"] * media_gb
    items.append(
        CostLineItem(
            name="S3 (media)",
            monthly_usd=round(s3_monthly, 2),
            basis=(
                f"measured media library size ({media_gb:.1f} GB)"
                if profile.media_library_size_mb
                else f"default estimate ({DEFAULT_MEDIA_LIBRARY_GB} GB, not measured)"
            ),
        )
    )

    monthly_page_views = profile.traffic.sessions_per_day * 30
    avg_page_weight_mb = profile.measured_avg_page_weight_mb or DEFAULT_AVG_PAGE_WEIGHT_MB
    estimated_cdn_gb = (monthly_page_views * avg_page_weight_mb) / 1024
    cache_hit_ratio = decision.cache_hit_ratio_used
    # CloudFront serves cache hits from edge; only the cache-miss fraction plus a
    # smaller steady trickle of edge-to-viewer transfer for hits is being approximated
    # here as a single blended discount factor, not split into origin vs edge pricing.
    billable_gb = estimated_cdn_gb * (1 - cache_hit_ratio * 0.5)
    cloudfront_monthly = _tiered_cloudfront_cost(billable_gb, pricing["cloudfront_tiered_pricing_usd_per_gb"])
    items.append(
        CostLineItem(
            name="CloudFront data transfer",
            monthly_usd=round(cloudfront_monthly, 2),
            basis=(
                f"estimated from {profile.traffic.sessions_per_day:,} sessions/day x "
                f"{avg_page_weight_mb:.2f} MB/page "
                f"({'measured from sampled pages' if profile.measured_avg_page_weight_mb else 'default assumption, not measured'}) "
                f"({billable_gb/1024:.1f} TB billable/month); uses AWS's actual tiered "
                f"per-GB pricing, not a flat rate, since the difference is large at this volume"
            ),
        )
    )

    total = round(sum(item.monthly_usd for item in items), 2)
    return CostEstimate(line_items=items, total_monthly_usd=total, pricing_source=source)


def _tiered_cloudfront_cost(total_gb: float, tiers: list[dict]) -> float:
    """Applies AWS's actual tiered CloudFront pricing structure (each tier's rate
    applies only to the GB within that tier, not the whole volume) rather than a flat
    per-GB rate, which would badly overestimate cost at high traffic volumes where the
    bulk of transfer falls into steep-discount tiers.
    """
    total_tb = total_gb / 1024
    cost = 0.0
    lower_bound_tb = 0.0

    for tier in tiers:
        upper_bound_tb = tier["up_to_tb"]
        if upper_bound_tb is None:
            tb_in_this_tier = max(total_tb - lower_bound_tb, 0)
        else:
            tb_in_this_tier = max(min(total_tb, upper_bound_tb) - lower_bound_tb, 0)
        cost += tb_in_this_tier * 1024 * tier["rate"]
        if upper_bound_tb is not None:
            lower_bound_tb = upper_bound_tb
        if upper_bound_tb is not None and total_tb <= upper_bound_tb:
            break

    return cost
