"""Compare paper experiment conditions with repository declarations.

Only static evidence is used: dependency manifests and documented run
commands. Anything that cannot be located is reported as
``missing_in_repository`` instead of being guessed.
"""

from __future__ import annotations

import math
import re

from app.models import (
    ComparisonStatus,
    DependencyInfo,
    Evidence,
    EvidenceKind,
    ExperimentCategory,
    ExperimentComparison,
    ExperimentComparisonItem,
    MissingItem,
    PaperReport,
    RepositoryEntryPoint,
    RepoInspectionResult,
)

GROUP_ALIASES: dict[str, frozenset[str]] = {
    "batch_size": frozenset(
        {"batch_size", "batchsize", "bs", "batch", "train_batch_size"}
    ),
    "learning_rate": frozenset(
        {
            "learning_rate",
            "learningrate",
            "lr",
            "initial_lr",
            "base_lr",
            "train_learning_rate",
        }
    ),
    "epochs": frozenset(
        {
            "epochs",
            "epoch",
            "num_epochs",
            "n_epochs",
            "max_epochs",
            "num_train_epochs",
            "train_epochs",
        }
    ),
    "seed": frozenset(
        {"seed", "seeds", "random_seed", "manual_seed", "torch_seed"}
    ),
    "optimizer": frozenset(
        {"optimizer", "optim", "opt", "optimizer_type", "optimizer_name"}
    ),
    "dataset": frozenset(
        {
            "dataset",
            "datasets",
            "data",
            "dataset_name",
            "data_dir",
            "data_path",
            "train_data",
        }
    ),
    "model": frozenset(
        {
            "model",
            "models",
            "model_name",
            "arch",
            "architecture",
            "backbone",
            "network",
        }
    ),
    "framework": frozenset(
        {"framework", "library", "lib", "backend", "toolkit"}
    ),
    "hardware": frozenset(
        {"hardware", "device", "gpu", "gpus", "accelerator", "cuda"}
    ),
    "precision": frozenset(
        {"precision", "dtype", "amp", "mixed_precision", "fp16", "bf16"}
    ),
    "weight_decay": frozenset({"weight_decay", "wd", "l2"}),
    "dropout": frozenset({"dropout", "dropout_rate"}),
}

NAME_TO_GROUP: dict[str, str] = {
    alias: group for group, aliases in GROUP_ALIASES.items() for alias in aliases
}

SHORT_FLAGS: dict[str, str] = {
    "b": "batch_size",
    "lr": "learning_rate",
    "e": "epochs",
    "s": "seed",
    "opt": "optimizer",
    "m": "model",
}

FRAMEWORK_ALIASES: dict[str, frozenset[str]] = {
    "pytorch": frozenset({"torch", "pytorch"}),
    "torch": frozenset({"torch", "pytorch"}),
    "tensorflow": frozenset({"tensorflow", "tensorflow-gpu"}),
    "tf": frozenset({"tensorflow", "tensorflow-gpu"}),
    "jax": frozenset({"jax", "flax"}),
    "keras": frozenset({"keras"}),
    "paddle": frozenset({"paddlepaddle", "paddle"}),
    "mxnet": frozenset({"mxnet"}),
    "mindspore": frozenset({"mindspore"}),
}

GENERIC_HARDWARE = frozenset({"cuda", "gpu", "cpu", "cuda:0", "gpus"})

VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)+")
FLAG_TOKEN_PATTERN = re.compile(r"^--?[A-Za-z]")

CATEGORY_GROUPS: dict[str, tuple[str, ...]] = {
    ExperimentCategory.DATASET.value: ("dataset",),
    ExperimentCategory.MODEL.value: ("model",),
    ExperimentCategory.FRAMEWORK.value: ("framework",),
    ExperimentCategory.HARDWARE.value: ("hardware",),
}


def canonical_name(value: str) -> str:
    """Normalise identifiers: ``Batch-Size`` -> ``batch_size``."""

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def canonical_dependency(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def group_of(name: str) -> str:
    canonical = canonical_name(name)
    return NAME_TO_GROUP.get(canonical, canonical)


def _normalise_value(value: str) -> str:
    text = value.strip().strip("`'\"").strip().rstrip(",.;")
    return re.sub(r"\s+", " ", text).lower()


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def values_match(paper_value: str, repo_value: str) -> bool:
    """Compare two values permitting ``256``/``256.0`` and ``1e-3``/``0.001``."""

    left = _normalise_value(paper_value)
    right = _normalise_value(repo_value)

    if left == right:
        return True

    left_float = _as_float(left)
    right_float = _as_float(right)
    if left_float is not None and right_float is not None:
        return math.isclose(left_float, right_float, rel_tol=1e-9)

    return False


def _flagged_values(
    entry_points: list[RepositoryEntryPoint],
) -> dict[str, list[tuple[str, list[Evidence]]]]:
    """Collect ``--flag value`` pairs keyed by canonical group name."""

    values: dict[str, list[tuple[str, list[Evidence]]]] = {}

    for entry_point in entry_points:
        if not entry_point.command:
            continue

        tokens = entry_point.command.split()
        for index, token in enumerate(tokens):
            name: str | None = None
            value: str | None = None

            if token.startswith("--") and len(token) > 2:
                body = token[2:]
                if "=" in body:
                    body, value = body.split("=", 1)
                name = body
            elif (
                token.startswith("-")
                and not token.startswith("--")
                and len(token) == 2
            ):
                name = SHORT_FLAGS.get(token[1])

            if name is None:
                continue

            if value is None and index + 1 < len(tokens):
                following = tokens[index + 1]
                if not FLAG_TOKEN_PATTERN.match(following):
                    value = following

            if value is None:
                continue

            cleaned = _normalise_value(value)
            if not cleaned:
                continue

            key = group_of(name)
            values.setdefault(key, []).append(
                (value.strip().strip("'\""), list(entry_point.evidence))
            )

    return values


def _lookup(
    values: dict[str, list[tuple[str, list[Evidence]]]],
    groups: tuple[str, ...],
) -> tuple[str, list[Evidence]] | None:
    for group in groups:
        found = values.get(group)
        if found:
            return found[0]
    return None


def _dependency_for_framework(
    paper_value: str, dependencies: list[DependencyInfo]
) -> DependencyInfo | None:
    tokens = [
        token
        for token in re.split(r"[^a-z0-9.]+", paper_value.lower())
        if token
    ]
    candidates: set[str] = set()
    for token in tokens:
        candidates.update(FRAMEWORK_ALIASES.get(token, frozenset()))

    if not candidates:
        candidates = {canonical_dependency(paper_value)} | set(tokens)

    for dependency in dependencies:
        if canonical_dependency(dependency.name) in candidates:
            return dependency

    for dependency in dependencies:
        if canonical_dependency(dependency.name) in tokens:
            return dependency

    return None


def _versions_compatible(paper_value: str, dependency: DependencyInfo) -> bool:
    paper_versions = VERSION_PATTERN.findall(paper_value)
    repo_versions = VERSION_PATTERN.findall(dependency.version or "")

    if not paper_versions or not repo_versions:
        return True

    return any(
        repo.startswith(paper) or paper.startswith(repo)
        for paper in paper_versions
        for repo in repo_versions
    )


class ExperimentComparer:
    """Build an ``ExperimentComparison`` from a paper and an inspection."""

    def compare(
        self,
        *,
        paper: PaperReport,
        repository: RepoInspectionResult,
    ) -> ExperimentComparison:
        parameters = paper.experiment_parameters
        flags = _flagged_values(repository.entry_points)
        dependencies = repository.dependencies

        items: list[ExperimentComparisonItem] = []
        missing: list[MissingItem] = []
        warnings: list[str] = []

        if not parameters:
            warnings.append(
                "论文中未抽取到实验参数，无法生成条件对比。"
            )

        if not dependencies and not repository.entry_points:
            warnings.append(
                "仓库中既未解析到依赖清单也未找到运行命令，"
                "对比结论可能偏向 missing_in_repository。"
            )

        for parameter in parameters:
            category = ExperimentCategory(parameter.category)
            evidence = list(parameter.evidence)
            note: str | None = None
            repo_value: str | None = None
            status = ComparisonStatus.UNKNOWN

            resolved = self._resolve_from_flags(
                parameter_value=parameter.value,
                parameter_name=parameter.name,
                category=category,
                flags=flags,
            )

            if resolved is not None:
                repo_value, flag_evidence = resolved
                evidence.extend(flag_evidence)
                status = (
                    ComparisonStatus.MATCH
                    if values_match(parameter.value, repo_value)
                    else ComparisonStatus.MISMATCH
                )
                if (
                    category is ExperimentCategory.HARDWARE
                    and status is ComparisonStatus.MISMATCH
                    and _normalise_value(repo_value) in GENERIC_HARDWARE
                ):
                    status = ComparisonStatus.UNKNOWN
                    note = "仓库只声明了设备类型，无法确认具体硬件型号"

            elif category is ExperimentCategory.FRAMEWORK:
                dependency = _dependency_for_framework(
                    parameter.value, dependencies
                )
                if dependency is not None:
                    repo_value = f"{dependency.name}{dependency.version or ''}"
                    evidence.append(dependency.source)
                    compatible = _versions_compatible(
                        parameter.value, dependency
                    )
                    status = (
                        ComparisonStatus.MATCH
                        if compatible
                        else ComparisonStatus.MISMATCH
                    )
                    if not dependency.version:
                        note = "依赖清单未声明版本"

            elif category in (
                ExperimentCategory.MODEL,
                ExperimentCategory.DATASET,
            ):
                dependency = _dependency_for_framework(
                    parameter.value, dependencies
                )
                if dependency is not None:
                    repo_value = f"{dependency.name}{dependency.version or ''}"
                    evidence.append(dependency.source)
                    status = ComparisonStatus.MATCH
                    note = "仅在依赖清单中匹配到同名依赖，未核对实际配置"

            if repo_value is None:
                status = ComparisonStatus.MISSING_IN_REPOSITORY
                missing.append(
                    MissingItem(
                        field=f"experiment_parameters.{parameter.name}",
                        description=(
                            f"论文中的实验参数 {parameter.name}="
                            f"{parameter.value} 未在仓库中找到对应声明"
                        ),
                        reason=(
                            "仓库依赖清单、运行命令和入口脚本中均未出现"
                            "该参数的取值"
                        ),
                    )
                )

            items.append(
                ExperimentComparisonItem(
                    name=parameter.name,
                    category=category,
                    paper_value=parameter.value,
                    repo_value=repo_value,
                    status=status,
                    evidence=evidence,
                    notes=note,
                )
            )

        if missing:
            warnings.append(
                f"有 {len(missing)} 项论文实验参数在仓库中缺失，"
                "复现前需要人工确认。"
            )

        return ExperimentComparison(
            items=items,
            missing_items=missing,
            warnings=warnings,
        )

    def _resolve_from_flags(
        self,
        *,
        parameter_value: str,
        parameter_name: str,
        category: ExperimentCategory,
        flags: dict[str, list[tuple[str, list[Evidence]]]],
    ) -> tuple[str, list[Evidence]] | None:
        groups = CATEGORY_GROUPS.get(category.value)
        if groups is None:
            groups = (group_of(parameter_name),)

        resolved = _lookup(flags, groups)
        if resolved is not None:
            return resolved

        name_group = group_of(parameter_name)
        if name_group not in groups:
            return _lookup(flags, (name_group,))

        return None


def build_evidence_from_command(
    *, locator: str, quote: str
) -> Evidence:
    """Convenience helper for callers that cite a documented command."""

    return Evidence(
        kind=EvidenceKind.REPO_FILE,
        locator=locator,
        quote=quote,
    )
