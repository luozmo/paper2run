from __future__ import annotations

import json
from pathlib import Path

from app.dsh_agent import PaperAnalysisRun
from app.models import (
    Evidence,
    EvidenceKind,
    ExperimentCategory,
    ExperimentParameter,
    PaperMetadata,
    PaperReport,
    RepoCandidate,
)
from scripts import run_paper as run_paper_module


class FakeAgent:
    def __init__(self, analysis: PaperAnalysisRun) -> None:
        self.analysis = analysis

    def analyze_pdf_with_context(
        self,
        pdf_path: Path,
        *,
        job_id: str,
    ) -> PaperAnalysisRun:
        assert pdf_path.is_file()
        assert job_id == "cli-job"
        return self.analysis


class LocalDiscovery:
    def __init__(self, repository_path: Path) -> None:
        self.repository_path = repository_path

    def discover(self, *, paper: PaperMetadata, paper_text: str):
        assert "https://github.com/example/local-repo" in paper_text
        return [
            RepoCandidate(
                url="https://github.com/example/local-repo",
                owner="example",
                name="local-repo",
                confidence=0.9,
            )
        ]

    def acquire(self, *, repo_url: str) -> Path:
        assert repo_url == "https://github.com/example/local-repo"
        return self.repository_path


def test_main_runs_full_pipeline(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "requirements.txt").write_text(
        "torch==2.1.0\n",
        encoding="utf-8",
    )
    (repository / "train.py").write_text(
        "if __name__ == '__main__':\n    pass\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        "python train.py --batch_size 128\n",
        encoding="utf-8",
    )

    workspace = tmp_path / "jobs" / "cli-job" / "workspace"
    workspace.mkdir(parents=True)
    paper_evidence = Evidence(
        kind=EvidenceKind.PAPER,
        locator="Experimental Setup",
        page=3,
        quote="We train with batch size 256.",
    )
    report = PaperReport(
        paper=PaperMetadata(
            title="CLI Integration Paper",
            evidence=[paper_evidence],
        ),
        experiment_parameters=[
            ExperimentParameter(
                name="batch_size",
                value="256",
                category=ExperimentCategory.TRAINING,
                evidence=[paper_evidence],
            )
        ],
    )
    analysis = PaperAnalysisRun(
        report=report,
        paper_text=(
            "We train with batch size 256.\n"
            "Code: https://github.com/example/local-repo"
        ),
        workspace=workspace,
    )

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        run_paper_module,
        "PaperAnalysisAgent",
        lambda *, model: FakeAgent(analysis),
    )
    monkeypatch.setattr(
        run_paper_module,
        "GitHubRepoDiscovery",
        lambda *, repository_root: LocalDiscovery(repository),
    )

    assert run_paper_module.main(
        [str(pdf_path), "--job-id", "cli-job"]
    ) == 0

    captured = capsys.readouterr()
    final_report = json.loads(captured.out)

    assert final_report["selected_repo_url"] == (
        "https://github.com/example/local-repo"
    )
    assert final_report["experiment_comparison"]["items"][0]["status"] == (
        "mismatch"
    )
    assert (workspace / "result.json").is_file()
    assert (workspace / "report" / "report.md").is_file()
    assert (workspace / "report" / "report.docx").is_file()
    assert "output:" in captured.err
