"""Repository inspection module boundary.

Implements ``app.interfaces.RepoInspectionService``: parse dependency
manifests, locate entry points and run commands, and compare paper
experiment conditions with what the repository actually declares.
"""

from __future__ import annotations

from app.repo_inspection.comparison import (
    ExperimentComparer,
    canonical_dependency,
    canonical_name,
    group_of,
    values_match,
)
from app.repo_inspection.service import (
    RepositoryInspectionError,
    RepositoryInspector,
)

__all__ = [
    "ExperimentComparer",
    "RepositoryInspectionError",
    "RepositoryInspector",
    "canonical_dependency",
    "canonical_name",
    "group_of",
    "values_match",
]

