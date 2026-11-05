from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    CodeAvailability,
    DependencyInfo,
    DependencyScope,
    Evidence,
    EvidenceKind,
    ExperimentCategory,
    ExperimentParameter,
    PaperMetadata,
    PaperReport,
    RepoCandidate,
    RepoOfficialStatus,
)


def test_report_json_round_trip() -> None:
    paper_evidence = Evidence(
        kind=EvidenceKind.PAPER,
        locator="Experimental Setup, paragraph 2",
        page=7,
        quote="We train with batch size 256 on 8 V100 GPUs.",
        confidence=0.98,
    )

    report = PaperReport(
        paper=PaperMetadata(
            title="Example Paper",
            authors=["Alice", "Bob"],
            year=2026,
            evidence=[paper_evidence],
        ),
        code_availability=CodeAvailability.FOUND,
        repo_candidates=[
            RepoCandidate(
                url="https://github.com/example/repo",
                owner="example",
                name="repo",
                official_status=RepoOfficialStatus.OFFICIAL,
                confidence=0.95,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.PAPER,
                        locator="Footnote 2",
                        page=1,
                        quote="Code is available at https://github.com/example/repo",
                    )
                ],
            )
        ],
        selected_repo_url="https://github.com/example/repo",
        dependencies=[
            DependencyInfo(
                name="torch",
                version="2.1.0",
                scope=DependencyScope.TRAINING,
                source=Evidence(
                    kind=EvidenceKind.MANIFEST,
                    locator="requirements.txt:1",
                    quote="torch==2.1.0",
                ),
                confidence=0.99,
            )
        ],
        experiment_parameters=[
            ExperimentParameter(
                name="batch_size",
                value="256",
                category=ExperimentCategory.TRAINING,
                evidence=[paper_evidence],
                confidence=0.98,
            )
        ],
    )

    payload = report.model_dump(mode="json")
    restored = PaperReport.model_validate(payload)

    assert restored.paper.title == "Example Paper"
    assert restored.code_availability == "found"
    assert restored.dependencies[0].name == "torch"
    assert restored.experiment_parameters[0].value == "256"


def test_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.PAPER,
            locator="page 1",
            confidence=1.5,
        )


def test_page_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.PAPER,
            locator="page 0",
            page=0,
        )