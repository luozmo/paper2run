"""Shared data models for Paper2Run."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceKind(str, Enum):
    PAPER = "paper"
    REPO_FILE = "repo_file"
    MANIFEST = "manifest"
    WEB = "web"
    RUN_LOG = "run_log"


class RepoOfficialStatus(str, Enum):
    OFFICIAL = "official"
    LIKELY_OFFICIAL = "likely_official"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class DependencyScope(str, Enum):
    CORE = "core"
    TRAINING = "training"
    EVALUATION = "evaluation"
    OPTIONAL = "optional"
    UNKNOWN = "unknown"


class CodeAvailability(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNCERTAIN = "uncertain"


class ManifestKind(str, Enum):
    REQUIREMENTS = "requirements"
    PYPROJECT = "pyproject"
    SETUP_PY = "setup_py"
    ENVIRONMENT = "environment"
    DOCKERFILE = "dockerfile"
    OTHER = "other"


class ComparisonStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_IN_REPOSITORY = "missing_in_repository"
    MISSING_IN_PAPER = "missing_in_paper"
    UNKNOWN = "unknown"


class ExperimentCategory(str, Enum):
    DATASET = "dataset"
    MODEL = "model"
    FRAMEWORK = "framework"
    HARDWARE = "hardware"
    TRAINING = "training"
    EVALUATION = "evaluation"
    OTHER = "other"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    kind: EvidenceKind
    locator: str = Field(min_length=1)
    quote: str | None = None
    url: str | None = None
    page: int | None = Field(default=None, ge=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PaperMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class RepoCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    url: str = Field(min_length=1)
    owner: str | None = None
    name: str | None = None
    official_status: RepoOfficialStatus = RepoOfficialStatus.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    notes: str | None = None


class DependencyInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(min_length=1)
    version: str | None = None
    scope: DependencyScope = DependencyScope.UNKNOWN
    source: Evidence
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ExperimentParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    category: ExperimentCategory = ExperimentCategory.OTHER
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MissingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reason: str | None = None


class RepoManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    path: str = Field(min_length=1)
    kind: ManifestKind = ManifestKind.OTHER
    evidence: Evidence


class RepositoryEntryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    command: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RepoInspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(min_length=1)
    readme_path: str | None = None
    manifests: list[RepoManifest] = Field(default_factory=list)
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    entry_points: list[RepositoryEntryPoint] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    structure_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExperimentComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(min_length=1)
    category: ExperimentCategory = ExperimentCategory.OTHER
    paper_value: str | None = None
    repo_value: str | None = None
    status: ComparisonStatus = ComparisonStatus.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)
    notes: str | None = None


class ExperimentComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    items: list[ExperimentComparisonItem] = Field(default_factory=list)
    missing_items: list[MissingItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PaperReport(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    paper: PaperMetadata
    code_availability: CodeAvailability = CodeAvailability.UNCERTAIN
    repo_candidates: list[RepoCandidate] = Field(default_factory=list)
    selected_repo_url: str | None = None
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    experiment_parameters: list[ExperimentParameter] = Field(
        default_factory=list
    )
    repo_inspection: RepoInspectionResult | None = None
    experiment_comparison: ExperimentComparison | None = None
    missing_items: list[MissingItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PdfPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str


class PdfDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    page_count: int = Field(ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)
    pages: list[PdfPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
