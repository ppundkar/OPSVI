"""Command line entry for scheduled automation."""

from __future__ import annotations

import argparse
import asyncio
import json

from agent.config import get_settings, load_rates
from agent.integrations.powerbi import push_powerbi
from agent.integrations.teams import notify_teams
from agent.models import OptimizeRequest
from agent.service import TtlCache, run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VOCE once")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--use-config", action="store_true")
    parser.add_argument("--notify-teams", action="store_true")
    parser.add_argument("--push-powerbi", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    request = OptimizeRequest(
        demo=args.demo,
        use_config=args.use_config,
        include_ai=True,
        notify_teams=False,
        push_powerbi=False,
        refresh=args.refresh,
    )
    settings = get_settings()
    result, _, _ = asyncio.run(run_analysis(request, settings, load_rates(), TtlCache()))
    if args.notify_teams:
        result.teams = asyncio.run(notify_teams(result, settings))
    if args.push_powerbi:
        result.powerbi = asyncio.run(
            push_powerbi(
                result,
                settings,
                [result.exports.powerbi_findings_csv, result.exports.powerbi_summary_csv],
            )
        )
    print(
        json.dumps(
            {
                "analysis_id": result.analysis_id,
                "conservative_monthly_usd": result.summary.conservative_monthly_usd,
                "annual_conservative_usd": result.summary.annual_conservative_usd,
                "finding_count": result.summary.finding_count,
                "duration_ms": result.duration_ms,
                "html": result.exports.html_path,
                "csv": result.exports.csv_path,
                "partial": result.partial,
                "teams": None if result.teams is None else result.teams.status,
                "powerbi": None if result.powerbi is None else result.powerbi.status,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
