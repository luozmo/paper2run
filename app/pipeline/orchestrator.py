"""Compose independent Paper2Run services into one pipeline."""

from __future__ import annotations

from pathlib import Path

from app.interfaces import (
    RepoDiscoveryService,
    RepoInspectionService,
    ReportRenderer,
)
from app.models import CodeAvailability, PaperReport


class Paper2RunPipeline:
    """Orchestrate repository discovery, inspection and rendering."""

    def __init__(
        self,
        *,
        discovery: RepoDiscoveryService,
        inspector: RepoInspectionService,
        renderer: ReportRenderer,
    ) -> None:
        self.discovery = discovery
        self.inspector = inspector
        self.renderer = renderer

    def run(
        self,
        *,
        paper: PaperReport,
        paper_text: str,
        output_dir: Path,
    ) -> tuple[PaperReport, list[Path]]:
        """Run all post-extraction stages and render the final report."""
        candidates = self.discovery.discover(
            paper=paper.paper,
            paper_text=paper_text,
        )

        selected_repo_url = paper.selected_repo_url
        if selected_repo_url is None and candidates:
            selected_repo_url = candidates[0].url

        report = paper.model_copy(
            update={
                "repo_candidates": candidates,
                "selected_repo_url": selected_repo_url,
            }
        )

        if selected_repo_url is None:
            outputs = self.renderer.render(
                report=report,
                output_dir=output_dir,
            )
            return report, outputs

        repository_path = self.discovery.acquire(
            repo_url=selected_repo_url,
        )
        inspection = self.inspector.inspect(
            repo_url=selected_repo_url,
            repository_path=repository_path,
        )
        comparison = self.inspector.compare(
            paper=report,
            repository=inspection,
        )

        report = report.model_copy(
            update={
                "code_availability": CodeAvailability.FOUND.value,
                "repo_inspection": inspection,
                "experiment_comparison": comparison,
            }
        )
        outputs = self.renderer.render(
            report=report,
            output_dir=output_dir,
        )
        return report, outputs
