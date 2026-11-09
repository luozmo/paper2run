from __future__ import annotations

from app.models import (
    ComparisonStatus,
    DependencyInfo,
    DependencyScope,
    Evidence,
    EvidenceKind,
    ExperimentCategory,
    ExperimentComparison,
    ExperimentComparisonItem,
    ManifestKind,
    RepoInspectionResult,
    RepoManifest,
    RepositoryEntryPoint,
)


def test_repo_inspection_result_round_trip() -> None:
    evidence = Evidence(
        kind=EvidenceKind.REPO_FILE,
        locator="requirements.txt:1",
        quote="torch==2.1.0",
    )
    inspection = RepoInspectionResult(
        repo_url="https://github.com/example/repo",
        readme_path="README.md",
        manifests=[
            RepoManifest(
                path="requirements.txt",
                kind=ManifestKind.REQUIREMENTS,
                evidence=evidence,
            )
        ],
        dependencies=[
            DependencyInfo(
                name="torch",
                version="2.1.0",
                scope=DependencyScope.TRAINING,
                source=evidence,
                confidence=0.99,
            )
        ],
        entry_points=[
            RepositoryEntryPoint(
                path="train.py",
                command="python train.py",
                evidence=[evidence],
                confidence=0.9,
            )
        ],
        run_commands=["python train.py"],
        structure_summary="A Python training repository.",
    )

    restored = RepoInspectionResult.model_validate(
        inspection.model_dump(mode="json")
    )

    assert restored.repo_url == inspection.repo_url
    assert restored.dependencies[0].name == "torch"
    assert restored.entry_points[0].command == "python train.py"


def test_experiment_comparison_round_trip() -> None:
    comparison = ExperimentComparison(
        items=[
            ExperimentComparisonItem(
                name="batch_size",
                category=ExperimentCategory.TRAINING,
                paper_value="256",
                repo_value="128",
                status=ComparisonStatus.MISMATCH,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.REPO_FILE,
                        locator="config.yaml:3",
                        quote="batch_size: 128",
                    )
                ],
                notes="Repository configuration differs from the paper.",
            )
        ]
    )

    restored = ExperimentComparison.model_validate(
        comparison.model_dump(mode="json")
    )

    assert restored.items[0].name == "batch_size"
    assert restored.items[0].status == ComparisonStatus.MISMATCH
    assert restored.items[0].paper_value == "256"
