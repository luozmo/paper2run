#!/usr/bin/env python3
"""Command-line entry point for one-paper analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.config import DSH_MODEL
from app.dsh_agent import PaperAnalysisAgent


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        agent = PaperAnalysisAgent(model=args.model)
        report = agent.analyze_pdf(
            args.pdf,
            job_id=args.job_id,
        )
    except Exception as exc:
        print(f"paper2run error: {exc}", file=sys.stderr)
        return 1

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())