"""Locate dependency manifests inside a repository checkout."""

from __future__ import annotations

import os
from pathlib import Path

from app.models import Evidence, EvidenceKind, ManifestKind, RepoManifest
from app.repo_inspection.files import relative_locator

SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".tox",
        ".nox",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "site-packages",
        "dist-packages",
        "__pycache__",
        "build",
        "dist",
        "docs",
        "examples",
        "example",
        "third_party",
    }
)

MANIFEST_FILENAMES: dict[str, ManifestKind] = {
    "requirements.txt": ManifestKind.REQUIREMENTS,
    "pyproject.toml": ManifestKind.PYPROJECT,
    "setup.py": ManifestKind.SETUP_PY,
    "setup.cfg": ManifestKind.OTHER,
    "environment.yml": ManifestKind.ENVIRONMENT,
    "environment.yaml": ManifestKind.ENVIRONMENT,
    "conda.yml": ManifestKind.ENVIRONMENT,
    "conda.yaml": ManifestKind.ENVIRONMENT,
    "dockerfile": ManifestKind.DOCKERFILE,
    "pipfile": ManifestKind.OTHER,
    "poetry.lock": ManifestKind.OTHER,
}

DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_MANIFESTS = 20


def classify_manifest(name: str) -> ManifestKind | None:
    """Map a file name to a manifest kind, or ``None`` when irrelevant."""

    lowered = name.lower()

    if lowered in MANIFEST_FILENAMES:
        return MANIFEST_FILENAMES[lowered]

    if lowered.endswith(".txt") and lowered.startswith("requirements"):
        return ManifestKind.REQUIREMENTS

    if lowered.startswith("dockerfile"):
        return ManifestKind.DOCKERFILE

    if lowered.startswith("environment") and lowered.endswith(
        (".yml", ".yaml")
    ):
        return ManifestKind.ENVIRONMENT

    return None


def discover_manifests(
    root: Path,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_manifests: int = DEFAULT_MAX_MANIFESTS,
) -> list[RepoManifest]:
    """Find manifests at the repository root or in shallow subdirectories."""

    root = Path(root)
    if not root.is_dir():
        return []

    base_depth = len(root.resolve().parts)
    found: list[RepoManifest] = []

    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.resolve().parts) - base_depth

        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and name.lower() not in SKIP_DIRECTORIES
        )
        if depth >= max_depth:
            dirnames[:] = []

        for filename in sorted(filenames):
            kind = classify_manifest(filename)
            if kind is None:
                continue

            path = current_path / filename
            locator = relative_locator(root, path)
            found.append(
                RepoManifest(
                    path=locator,
                    kind=kind,
                    evidence=Evidence(
                        kind=EvidenceKind.REPO_FILE,
                        locator=locator,
                        confidence=1.0,
                    ),
                )
            )

            if len(found) >= max_manifests:
                return found

    return found
