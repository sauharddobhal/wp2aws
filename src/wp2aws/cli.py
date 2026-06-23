"""CLI entrypoint.

    python -m wp2aws demo
    python -m wp2aws scan https://example.com --sessions-per-day 50000
    python -m wp2aws scan --local --access-log /var/log/nginx/access.log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import ContentProfile, ScanMode, SiteProfile, TrafficProfile
from .report import render_markdown_report, render_text_report
from .scanners.local import LocalScanner
from .scanners.remote import RemoteScanner, RobotsDisallowedError
from .sizing.cost import estimate_cost
from .sizing.engine import compute_sizing
from .sizing.tfvars import render_tfvars

DEMO_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "demo_site.json"


def _load_demo_profile() -> SiteProfile:
    data = json.loads(DEMO_DATA_PATH.read_text(encoding="utf-8"))
    return SiteProfile(
        source_url=data["source_url"],
        scan_mode=ScanMode.DEMO,
        traffic=TrafficProfile(
            sessions_per_day=data["sessions_per_day"],
            peak_to_average_ratio=data["peak_to_average_ratio"],
            measured=False,
        ),
        content_profile=ContentProfile(data["content_profile"]),
        plugins=data["plugins"],
        plugin_detection_exhaustive=False,
        post_count=data.get("post_count"),
        page_count=data.get("page_count"),
        database_size_mb=data.get("database_size_mb"),
        media_library_size_mb=data.get("media_library_size_mb"),
        server_cpu_cores=data.get("server_cpu_cores"),
        server_ram_mb=data.get("server_ram_mb"),
        server_disk_gb=data.get("server_disk_gb"),
        notes=data.get("notes", []),
    )


def _run_pipeline(profile: SiteProfile, aws_region: str, use_live_pricing: bool) -> tuple:
    decision = compute_sizing(profile)
    cost = estimate_cost(decision, profile, use_live_pricing=use_live_pricing)
    return decision, cost


def _output(profile, decision, cost, export_tfvars, export_report, aws_region, current_hosting_cost_usd=None):
    print(render_text_report(profile, decision, cost, current_hosting_cost_usd))

    if export_tfvars:
        Path(export_tfvars).write_text(render_tfvars(decision, profile, aws_region), encoding="utf-8")
        print(f"\nWrote {export_tfvars}")

    if export_report:
        Path(export_report).write_text(
            render_markdown_report(profile, decision, cost, current_hosting_cost_usd), encoding="utf-8"
        )
        print(f"Wrote {export_report}")


def cmd_demo(args: argparse.Namespace) -> int:
    profile = _load_demo_profile()
    decision, cost = _run_pipeline(profile, args.aws_region, args.live_pricing)
    _output(
        profile, decision, cost, args.export_tfvars, args.export_report, args.aws_region,
        current_hosting_cost_usd=args.current_hosting_cost,
    )
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    if args.local:
        scanner = LocalScanner()
        profile = scanner.scan(access_log_path=args.access_log)
        if profile.traffic.sessions_per_day == 0:
            print(
                "Warning: no --access-log provided in local mode, traffic is unset. "
                "Pass --access-log /path/to/access.log for a measured figure.",
                file=sys.stderr,
            )
    else:
        if not args.url:
            print("Error: a URL is required for remote scan mode.", file=sys.stderr)
            return 1
        if args.sessions_per_day is None:
            print(
                "Error: --sessions-per-day is required in remote mode. There is no "
                "honest way to measure real traffic from outside a site; see README.",
                file=sys.stderr,
            )
            return 1
        scanner = RemoteScanner()
        try:
            profile = scanner.scan(args.url, sessions_per_day=args.sessions_per_day)
        except RobotsDisallowedError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    decision, cost = _run_pipeline(profile, args.aws_region, args.live_pricing)
    _output(
        profile, decision, cost, args.export_tfvars, args.export_report, args.aws_region,
        current_hosting_cost_usd=args.current_hosting_cost,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wp2aws", description="WordPress-to-AWS migration sizing tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="Run against bundled synthetic data, zero network calls.")
    demo_parser.add_argument("--aws-region", default="us-east-1")
    demo_parser.add_argument("--live-pricing", action="store_true")
    demo_parser.add_argument("--export-tfvars", default=None)
    demo_parser.add_argument("--export-report", default=None)
    demo_parser.add_argument("--current-hosting-cost", type=float, default=None, help="Current monthly hosting cost in USD, for a savings comparison.")
    demo_parser.set_defaults(func=cmd_demo)

    scan_parser = subparsers.add_parser("scan", help="Scan a real site, remotely or locally.")
    scan_parser.add_argument("url", nargs="?", default=None, help="Site URL (remote mode only).")
    scan_parser.add_argument("--local", action="store_true", help="Run as a local/server-side scan instead.")
    scan_parser.add_argument("--access-log", default=None, help="Path to an access log (local mode).")
    scan_parser.add_argument("--sessions-per-day", type=int, default=None, help="Required in remote mode.")
    scan_parser.add_argument("--aws-region", default="us-east-1")
    scan_parser.add_argument("--live-pricing", action="store_true")
    scan_parser.add_argument("--export-tfvars", default=None)
    scan_parser.add_argument("--export-report", default=None)
    scan_parser.add_argument("--current-hosting-cost", type=float, default=None, help="Current monthly hosting cost in USD, for a savings comparison.")
    scan_parser.set_defaults(func=cmd_scan)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
