#!/usr/bin/env python3
"""Command-line entry point for one-paper analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.config import DSH_MODEL
from app.dsh_agent import PaperAnalysisAgent
from app.pipeline import Paper2RunPipeline
from app.repo_discovery import GitHubRepoDiscovery
from app.repo_inspection import RepositoryInspector
from app.reporting import PaperReportRenderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze one paper PDF and generate a structured PaperReport."
        )
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the paper PDF.",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional safe job ID. A random ID is generated when omitted.",
    )
    parser.add_argument(
        "--model",
        default=DSH_MODEL,
        help=f"DSH model name. Default: {DSH_MODEL}",
    )
    parser.add_argument(
        "--repo-url",
        default=None,
        help=(
            "Optional GitHub repository URL to override automatic discovery."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        agent = PaperAnalysisAgent(model=args.model)
        analysis = agent.analyze_pdf_with_context(
            args.pdf,
            job_id=args.job_id,
        )

        report = analysis.report
        if args.repo_url:
            report = report.model_copy(
                update={"selected_repo_url": args.repo_url}
            )

        job_dir = analysis.workspace.parent
        pipeline = Paper2RunPipeline(
            discovery=GitHubRepoDiscovery(
                repository_root=job_dir / "repositories",
            ),
            inspector=RepositoryInspector(),
            renderer=PaperReportRenderer(),
        )

        report, report_paths = pipeline.run(
            paper=report,
            paper_text=analysis.paper_text,
            output_dir=analysis.workspace / "report",
        )

        (analysis.workspace / "result.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"paper2run error: {exc}", file=sys.stderr)
        return 1

    print(report.model_dump_json(indent=2))
    for path in report_paths:
        print(f"output: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
