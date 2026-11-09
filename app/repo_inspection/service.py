"""Static inspection of a repository checkout.

This service implements ``app.interfaces.RepoInspectionService``. It never
downloads anything: ``repository_path`` is produced by the discovery module
(module 2) and only read here.
"""

from __future__ import annotations

from pathlib import Path

from app.models import (
    ExperimentComparison,
    ManifestKind,
    PaperReport,
    RepoInspectionResult,
)
from app.repo_inspection.comparison import ExperimentComparer
from app.repo_inspection.dependencies import (
    DEFAULT_MAX_DEPENDENCIES,
    collect_dependencies,
)
from app.repo_inspection.entrypoints import (
    DEFAULT_MAX_ENTRY_POINTS,
    DEFAULT_MAX_RUN_COMMANDS,
    extract_run_commands,
    find_entry_points,
    find_readme,
)
from app.repo_inspection.files import read_text, relative_locator
from app.repo_inspection.manifests import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_MANIFESTS,
    discover_manifests,
)

LANGUAGE_SUFFIXES: dict[str, str] = {
    ".py": "Python",
    ".ipynb": "Jupyter",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".ts": "TypeScript",
    ".js": "JavaScript",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
}

MAX_TOP_LEVEL_ENTRIES = 8


class RepositoryInspectionError(RuntimeError):
    """Raised when a repository cannot be inspected at all."""


class RepositoryInspector:
    """Inspect a local checkout and compare it with the paper."""

    def __init__(
        self,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_manifests: int = DEFAULT_MAX_MANIFESTS,
        max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
        max_entry_points: int = DEFAULT_MAX_ENTRY_POINTS,
        max_run_commands: int = DEFAULT_MAX_RUN_COMMANDS,
        comparer: ExperimentComparer | None = None,
    ) -> None:
        self.max_depth = max_depth
        self.max_manifests = max_manifests
        self.max_dependencies = max_dependencies
        self.max_entry_points = max_entry_points
        self.max_run_commands = max_run_commands
        self.comparer = comparer or ExperimentComparer()

    def inspect(
        self,
        *,
        repo_url: str,
        repository_path: Path,
    ) -> RepoInspectionResult:
        """Read manifests, dependencies and entry points from a checkout."""

        url = (repo_url or "").strip()
        if not url:
            raise RepositoryInspectionError("repo_url 不能为空")

        root = Path(repository_path)
        if not root.exists():
            raise RepositoryInspectionError(f"仓库路径不存在：{root}")
        if not root.is_dir():
            raise RepositoryInspectionError(f"仓库路径不是目录：{root}")

        warnings: list[str] = []

        manifests = discover_manifests(
            root,
            max_depth=self.max_depth,
            max_manifests=self.max_manifests,
        )
        dependencies, dependency_warnings = collect_dependencies(
            root,
            manifests,
            max_dependencies=self.max_dependencies,
        )
        warnings.extend(dependency_warnings)

        readme_path = find_readme(root)
        readme_relative = (
            relative_locator(root, readme_path) if readme_path else None
        )

        documented: list[tuple[int, str]] = []
        if readme_path is None:
            warnings.append("仓库根目录未找到 README，运行命令可能不完整")
        else:
            readme_text = read_text(readme_path) or ""
            documented = extract_run_commands(
                readme_text,
                max_commands=self.max_run_commands,
            )

        entry_points = find_entry_points(
            root,
            documented_commands=documented,
            readme_path=readme_path,
            max_entry_points=self.max_entry_points,
        )

        run_commands = [command for _, command in documented]
        if not run_commands:
            run_commands = [
                entry_point.command
                for entry_point in entry_points
                if entry_point.command
            ][: self.max_run_commands]

        if not manifests:
            warnings.append("仓库中未找到依赖清单文件")
        if not entry_points:
            warnings.append("仓库中未发现明显的入口脚本")
        if not run_commands:
            warnings.append("未从 README 或入口脚本中提取到运行命令")

        summary = _summarize(
            root=root,
            manifests=manifests,
            dependency_count=len(dependencies),
            entry_point_count=len(entry_points),
            run_command_count=len(run_commands),
            has_readme=readme_path is not None,
        )

        return RepoInspectionResult(
            repo_url=url,
            readme_path=readme_relative,
            manifests=manifests,
            dependencies=dependencies,
            entry_points=entry_points,
            run_commands=run_commands,
            structure_summary=summary,
            warnings=warnings,
        )

    def compare(
        self,
        *,
        paper: PaperReport,
        repository: RepoInspectionResult,
    ) -> ExperimentComparison:
        """Compare paper experiment conditions against the repository."""

        return self.comparer.compare(paper=paper, repository=repository)


def _detect_language(root: Path, manifests: list) -> str | None:
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []

    counts: dict[str, int] = {}
    for entry in entries:
        if not entry.is_file():
            continue
        language = LANGUAGE_SUFFIXES.get(entry.suffix.lower())
        if language is not None:
            counts[language] = counts.get(language, 0) + 1

    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]

    kinds = {ManifestKind(str(manifest.kind)) for manifest in manifests}
    if kinds & {
        ManifestKind.PYPROJECT,
        ManifestKind.SETUP_PY,
        ManifestKind.REQUIREMENTS,
    }:
        return "Python"

    return None


def _top_level_directories(root: Path) -> list[str]:
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []

    names = [
        entry.name
        for entry in entries
        if entry.is_dir() and not entry.name.startswith(".")
    ]
    return names[:MAX_TOP_LEVEL_ENTRIES]


def _summarize(
    *,
    root: Path,
    manifests: list,
    dependency_count: int,
    entry_point_count: int,
    run_command_count: int,
    has_readme: bool,
) -> str:
    parts: list[str] = []

    language = _detect_language(root, manifests)
    parts.append(f"{language} 仓库" if language else "通用仓库")

    directories = _top_level_directories(root)
    if directories:
        parts.append(f"顶层目录：{'、'.join(directories)}")

    if manifests:
        kinds = sorted({str(manifest.path) for manifest in manifests})
        parts.append(f"依赖清单 {len(manifests)} 个（{'、'.join(kinds)}）")
    else:
        parts.append("未发现依赖清单")

    parts.append(f"依赖 {dependency_count} 项")
    parts.append(f"入口脚本 {entry_point_count} 个")
    parts.append(f"运行命令 {run_command_count} 条")
    parts.append("含 README" if has_readme else "无 README")

    return "；".join(parts) + "。"
