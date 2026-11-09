"""Cross-module service contracts for Paper2Run."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.models import (
    ExperimentComparison,
    PaperMetadata,
    PaperReport,
    RepoCandidate,
    RepoInspectionResult,
)


class RepoDiscoveryService(Protocol):
    """Find, rank and acquire repository candidates for one paper."""

    def discover(
        self,
        *,
        paper: PaperMetadata,
        paper_text: str,
    ) -> list[RepoCandidate]:
        ...

    def acquire(self, *, repo_url: str) -> Path:
        ...


class RepoInspectionService(Protocol):
    """Inspect repositories and compare reproduction conditions."""

    def inspect(
        self,
        *,
        repo_url: str,
        repository_path: Path,
    ) -> RepoInspectionResult:
        ...

    def compare(
        self,
        *,
        paper: PaperReport,
        repository: RepoInspectionResult,
    ) -> ExperimentComparison:
        ...


class ReportRenderer(Protocol):
    """Render the final report into one or more output files."""

    def render(
        self,
        *,
        report: PaperReport,
        output_dir: Path,
    ) -> list[Path]:
        ...
