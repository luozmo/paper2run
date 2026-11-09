from __future__ import annotations

from pathlib import Path

from app.models import (
    ExperimentComparison,
    ExperimentComparisonItem,
    PaperMetadata,
    PaperReport,
    RepoCandidate,
    RepoInspectionResult,
    RepoOfficialStatus,
)
from app.pipeline import Paper2RunPipeline


class FakeDiscovery:
    def discover(self, *, paper: PaperMetadata, paper_text: str):
        assert paper.title == "Example Paper"
        assert paper_text == "Full paper text"
        return [
            RepoCandidate(
                url="https://github.com/example/repo",
                owner="example",
                name="repo",
                official_status=RepoOfficialStatus.LIKELY_OFFICIAL,
                confidence=0.9,
            )
        ]

    def acquire(self, *, repo_url: str) -> Path:
        assert repo_url == "https://github.com/example/repo"
        return Path("example-repo")


class FakeInspector:
    def inspect(
        self,
        *,
        repo_url: str,
        repository_path: Path,
    ) -> RepoInspectionResult:
        assert repo_url == "https://github.com/example/repo"
        assert repository_path == Path("example-repo")
        return RepoInspectionResult(
            repo_url=repo_url,
            run_commands=["python train.py"],
        )

    def compare(
        self,
        *,
        paper: PaperReport,
        repository: RepoInspectionResult,
    ) -> ExperimentComparison:
        assert paper.paper.title == "Example Paper"
        assert repository.repo_url == "https://github.com/example/repo"
        return ExperimentComparison(
            items=[
                ExperimentComparisonItem(
                    name="batch_size",
                    paper_value="256",
                    repo_value="256",
                    status="match",
                )
            ]
        )


class FakeRenderer:
    def __init__(self) -> None:
        self.report: PaperReport | None = None

    def render(
        self,
        *,
        report: PaperReport,
        output_dir: Path,
    ) -> list[Path]:
        self.report = report
        return [output_dir / "report.md"]


def test_pipeline_connects_all_service_boundaries(tmp_path: Path) -> None:
    renderer = FakeRenderer()
    pipeline = Paper2RunPipeline(
        discovery=FakeDiscovery(),
        inspector=FakeInspector(),
        renderer=renderer,
    )
    paper = PaperReport(
        paper=PaperMetadata(
            title="Example Paper",
            authors=["Alice"],
        )
    )

    report, outputs = pipeline.run(
        paper=paper,
        paper_text="Full paper text",
        output_dir=tmp_path,
    )

    assert report.selected_repo_url == "https://github.com/example/repo"
    assert report.code_availability == "found"
    assert report.repo_inspection is not None
    assert report.experiment_comparison is not None
    assert report.experiment_comparison.items[0].status == "match"
    assert renderer.report == report
    assert outputs == [tmp_path / "report.md"]
