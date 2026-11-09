"""Parse dependency declarations out of repository manifests.

The parsers are deliberately tolerant: a malformed line becomes a warning,
never an exception. Only the standard library is used so this module adds
no third-party dependency to the project.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models import (
    DependencyInfo,
    DependencyScope,
    Evidence,
    EvidenceKind,
    ManifestKind,
    RepoManifest,
)
from app.repo_inspection.files import (
    line_locator,
    read_text,
    relative_locator,
)

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]

DEFAULT_MAX_DEPENDENCIES = 300

REQUIREMENT_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*"
    r"(?P<spec>[<>=!~][^;]*)?"
)

SETUP_BLOCK_PATTERN = re.compile(
    r"install_requires\s*=\s*\[(?P<body>.*?)\]",
    re.DOTALL,
)
QUOTED_PATTERN = re.compile(r"['\"]([^'\"]+)['\"]")

PYPROJECT_FALLBACK_PATTERN = re.compile(
    r"dependencies\s*=\s*\[(?P<body>.*?)\]",
    re.DOTALL,
)

FROM_PATTERN = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)"
    r"(?:\s+[Aa][Ss]\s+(?P<alias>[^\s#]+))?",
    re.IGNORECASE,
)
RUN_PIP_PATTERN = re.compile(
    r"^\s*RUN\s+.*?pip[0-9.]*\s+install\s+(?P<args>.+)$",
    re.IGNORECASE,
)

TRAINING_HINTS = frozenset(
    {
        "torch",
        "pytorch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorflow-gpu",
        "keras",
        "jax",
        "flax",
        "transformers",
        "accelerate",
        "deepspeed",
        "lightning",
        "pytorch-lightning",
        "mxnet",
        "paddlepaddle",
        "paddle",
        "apex",
        "xformers",
        "triton",
        "wandb",
        "tensorboard",
        "datasets",
        "tokenizers",
        "sentencepiece",
        "vllm",
        "diffusers",
        "timm",
        "mmcv",
        "mmdet",
        "detectron2",
    }
)

EVALUATION_HINTS = frozenset(
    {
        "evaluate",
        "scikit-learn",
        "sklearn",
        "torchmetrics",
        "rouge-score",
        "nltk",
        "bert-score",
        "sacrebleu",
        "jiwer",
        "pycocotools",
        "lm-eval",
    }
)

DEV_HINTS = frozenset(
    {
        "pytest",
        "pytest-cov",
        "coverage",
        "black",
        "ruff",
        "flake8",
        "isort",
        "mypy",
        "pylint",
        "pre-commit",
        "sphinx",
        "tox",
        "nox",
        "twine",
        "build",
    }
)

CORE_HINTS = frozenset(
    {
        "numpy",
        "scipy",
        "pandas",
        "pillow",
        "opencv-python",
        "opencv-python-headless",
        "opencv",
        "tqdm",
        "pyyaml",
        "yaml",
        "requests",
        "httpx",
        "hydra-core",
        "omegaconf",
        "einops",
        "matplotlib",
        "seaborn",
        "h5py",
        "imageio",
        "numba",
        "protobuf",
        "regex",
        "filelock",
        "packaging",
    }
)


def canonical_name(name: str) -> str:
    """Normalise a dependency name following PEP 503 conventions."""

    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _logical_lines(text: str):
    """Yield ``(line_number, joined_line)`` merging backslash continuations."""

    buffer: list[str] = []
    start = 0

    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.rstrip()
        if not buffer:
            start = number

        if stripped.endswith("\\"):
            buffer.append(stripped[:-1])
            continue

        buffer.append(stripped)
        yield start, " ".join(part.strip() for part in buffer if part.strip())
        buffer = []

    if buffer:
        yield start, " ".join(part.strip() for part in buffer if part.strip())


def _parse_requirement(text: str) -> tuple[str, str | None] | None:
    """Split ``torch==2.1.0`` into ``("torch", "==2.1.0")``."""

    candidate = text.strip()
    if not candidate or candidate.startswith("#"):
        return None

    candidate = candidate.split("#", 1)[0].strip()
    if not candidate:
        return None

    lowered = candidate.lower()
    if lowered.startswith(
        ("-", "git+", "http://", "https://", "file:", ".", "~")
    ):
        return None

    candidate = candidate.split(";", 1)[0].strip()
    match = REQUIREMENT_PATTERN.match(candidate)
    if match is None:
        return None

    name = match.group("name")
    spec = (match.group("spec") or "").strip()
    return name, spec or None


def _infer_scope(
    name: str,
    *,
    manifest_kind: ManifestKind | str,
    group: str | None = None,
    path: str = "",
) -> DependencyScope:
    """Heuristically label where a dependency is used."""

    canonical = canonical_name(name)
    lowered_path = path.lower()

    if group is not None:
        lowered_group = group.lower()
        if "train" in lowered_group:
            return DependencyScope.TRAINING
        if "eval" in lowered_group:
            return DependencyScope.EVALUATION

    if canonical in DEV_HINTS:
        return DependencyScope.OPTIONAL
    if canonical in TRAINING_HINTS:
        return DependencyScope.TRAINING
    if canonical in EVALUATION_HINTS:
        return DependencyScope.EVALUATION

    kind = ManifestKind(manifest_kind)
    if "dev" in lowered_path or "test" in lowered_path:
        return DependencyScope.OPTIONAL
    if kind is ManifestKind.DOCKERFILE:
        return DependencyScope.CORE

    if canonical == "python":
        return DependencyScope.CORE
    if canonical in CORE_HINTS:
        return DependencyScope.CORE

    return DependencyScope.UNKNOWN


def _build(
    *,
    root: Path,
    relative: str,
    name: str,
    version: str | None,
    line_number: int | None,
    quote: str,
    scope: DependencyScope,
) -> DependencyInfo:
    path = root / relative
    locator = (
        line_locator(root, path, line_number)
        if line_number is not None
        else relative_locator(root, path)
    )
    return DependencyInfo(
        name=name,
        version=version,
        scope=scope,
        source=Evidence(
            kind=EvidenceKind.MANIFEST,
            locator=locator,
            quote=quote[:200],
            confidence=0.9 if version else 0.7,
        ),
        confidence=0.9 if version else 0.7,
    )


def _find_line(
    text: str, *, requirement: str | None, name: str
) -> int | None:
    """Locate the line declaring a dependency.

    Exact requirement strings win over bare names, so ``build`` does not
    resolve to the ``[build-system]`` header.
    """

    lines = text.splitlines()

    if requirement:
        needle = requirement.strip().strip("'\"").lower()
        quoted_variants = (
            f'"{needle}"',
            f"'{needle}'",
            f'"{needle}',
            f"'{needle}",
        )
        for variant in quoted_variants:
            for number, raw in enumerate(lines, 1):
                if variant in raw.lower():
                    return number

        for number, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if stripped.startswith("["):
                continue
            if needle in raw.lower() and ('"' in raw or "'" in raw):
                return number

    quoted_name = re.compile(
        rf"['\"]{re.escape(name)}", re.IGNORECASE
    )
    for number, raw in enumerate(lines, 1):
        if quoted_name.search(raw):
            return number

    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("["):
            continue
        if re.search(
            rf"(^|[^A-Za-z0-9_.-]){re.escape(name)}([^A-Za-z0-9_.-]|$)",
            stripped,
            re.IGNORECASE,
        ) and ("=" in stripped or ":" in stripped):
            return number

    return None


def _parse_requirements(
    root: Path, manifest: RepoManifest, text: str
) -> list[DependencyInfo]:
    dependencies: list[DependencyInfo] = []

    for number, line in _logical_lines(text):
        parsed = _parse_requirement(line)
        if parsed is None:
            continue

        name, version = parsed
        dependencies.append(
            _build(
                root=root,
                relative=manifest.path,
                name=name,
                version=version,
                line_number=number,
                quote=line.strip(),
                scope=_infer_scope(
                    name,
                    manifest_kind=manifest.kind,
                    path=manifest.path,
                ),
            )
        )

    return dependencies


def _parse_pyproject(
    root: Path, manifest: RepoManifest, text: str
) -> tuple[list[DependencyInfo], list[str]]:
    dependencies: list[DependencyInfo] = []
    warnings: list[str] = []
    entries: list[tuple[str, str | None, str | None, str | None]] = []

    if tomllib is None:  # pragma: no cover - Python 3.10 fallback
        for match in PYPROJECT_FALLBACK_PATTERN.finditer(text):
            for quoted in QUOTED_PATTERN.findall(match.group("body")):
                parsed = _parse_requirement(quoted)
                if parsed is not None:
                    entries.append((parsed[0], parsed[1], None, quoted))
        if not entries:
            warnings.append(f"{manifest.path} 无法解析：当前 Python 无 TOML 支持")
    else:
        try:
            data = tomllib.loads(text)
        except Exception:
            return [], [f"{manifest.path} 无法解析：TOML 语法错误"]

        project = data.get("project") or {}
        for requirement in project.get("dependencies") or []:
            parsed = _parse_requirement(str(requirement))
            if parsed is not None:
                entries.append(
                    (parsed[0], parsed[1], None, str(requirement))
                )

        optional = project.get("optional-dependencies") or {}
        for group, requirements in optional.items():
            for requirement in requirements or []:
                parsed = _parse_requirement(str(requirement))
                if parsed is not None:
                    entries.append(
                        (parsed[0], parsed[1], str(group), str(requirement))
                    )

        poetry = (data.get("tool") or {}).get("poetry") or {}
        for name, spec in (poetry.get("dependencies") or {}).items():
            raw = f"{name}{spec}" if isinstance(spec, str) else str(name)
            if str(name).lower() == "python":
                entries.append((str(name), raw, None, raw))
                continue
            parsed = _parse_requirement(raw)
            if parsed is not None:
                entries.append((parsed[0], parsed[1], None, raw))

    lines = text.splitlines()
    for name, version, group, raw in entries:
        line_number = _find_line(
            text, requirement=raw, name=name
        )
        quote = (
            lines[line_number - 1].strip()
            if line_number is not None and line_number <= len(lines)
            else (raw or name)
        )
        dependencies.append(
            _build(
                root=root,
                relative=manifest.path,
                name=name,
                version=version,
                line_number=line_number,
                quote=quote or name,
                scope=_infer_scope(
                    name,
                    manifest_kind=manifest.kind,
                    group=group,
                    path=manifest.path,
                ),
            )
        )

    return dependencies, warnings


def _parse_setup_py(
    root: Path, manifest: RepoManifest, text: str
) -> list[DependencyInfo]:
    match = SETUP_BLOCK_PATTERN.search(text)
    if match is None:
        return []

    body = match.group("body")
    body_offset = match.start("body")
    dependencies: list[DependencyInfo] = []

    for quoted in QUOTED_PATTERN.finditer(body):
        parsed = _parse_requirement(quoted.group(1))
        if parsed is None:
            continue

        name, version = parsed
        absolute = body_offset + quoted.start()
        line_number = text.count("\n", 0, absolute) + 1
        dependencies.append(
            _build(
                root=root,
                relative=manifest.path,
                name=name,
                version=version,
                line_number=line_number,
                quote=quoted.group(1),
                scope=_infer_scope(
                    name,
                    manifest_kind=manifest.kind,
                    path=manifest.path,
                ),
            )
        )

    return dependencies


def _split_conda_requirement(token: str) -> tuple[str, str | None] | None:
    candidate = token.strip().strip("'\"")
    if not candidate or candidate.startswith("#"):
        return None

    if "::" in candidate:
        candidate = candidate.split("::", 1)[1]

    match = re.match(
        r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
        r"\s*(?P<spec>[=<>!~].*)?$",
        candidate,
    )
    if match is None:
        return None

    spec = (match.group("spec") or "").strip()
    return match.group("name"), spec or None


def _parse_environment(
    root: Path, manifest: RepoManifest, text: str
) -> list[DependencyInfo]:
    dependencies: list[DependencyInfo] = []
    in_dependencies = False

    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not raw.startswith((" ", "\t", "-")):
            in_dependencies = stripped.startswith("dependencies:")
            continue

        if not in_dependencies or not stripped.startswith("- "):
            continue

        token = stripped[2:].strip()
        if token in {"pip", "pip:"}:
            continue

        parsed = _split_conda_requirement(token)
        if parsed is None:
            continue

        name, version = parsed
        dependencies.append(
            _build(
                root=root,
                relative=manifest.path,
                name=name,
                version=version,
                line_number=number,
                quote=stripped,
                scope=_infer_scope(
                    name,
                    manifest_kind=manifest.kind,
                    path=manifest.path,
                ),
            )
        )

    return dependencies


def _split_image_reference(image: str) -> tuple[str, str | None]:
    if "@" in image:
        name, digest = image.split("@", 1)
        return name, digest

    head, separator, tail = image.rpartition(":")
    if separator and "/" not in tail:
        return head, tail

    return image, None


def _parse_dockerfile(
    root: Path, manifest: RepoManifest, text: str
) -> list[DependencyInfo]:
    dependencies: list[DependencyInfo] = []
    stage_aliases: set[str] = set()

    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        from_match = FROM_PATTERN.match(raw)
        if from_match is not None:
            image = from_match.group("image")
            alias = from_match.group("alias")
            lowered = image.lower()

            if alias:
                stage_aliases.add(alias.lower())

            unresolved = "$" in image
            is_stage_reference = (
                lowered in stage_aliases
                or lowered.split(":", 1)[0] in stage_aliases
            )

            if unresolved or is_stage_reference or lowered == "scratch":
                continue

            name, version = _split_image_reference(image)
            dependencies.append(
                _build(
                    root=root,
                    relative=manifest.path,
                    name=name,
                    version=version,
                    line_number=number,
                    quote=stripped,
                    scope=DependencyScope.CORE,
                )
            )
            continue

        pip_match = RUN_PIP_PATTERN.match(raw)
        if pip_match is None:
            continue

        for token in pip_match.group("args").split():
            if token.startswith("-"):
                continue
            parsed = _parse_requirement(token)
            if parsed is None:
                continue
            name, version = parsed
            dependencies.append(
                _build(
                    root=root,
                    relative=manifest.path,
                    name=name,
                    version=version,
                    line_number=number,
                    quote=stripped,
                    scope=_infer_scope(
                        name,
                        manifest_kind=manifest.kind,
                        path=manifest.path,
                    ),
                )
            )

    return dependencies


def collect_dependencies(
    root: Path,
    manifests: list[RepoManifest],
    *,
    max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
) -> tuple[list[DependencyInfo], list[str]]:
    """Parse every manifest, de-duplicated by name and version."""

    root = Path(root)
    dependencies: list[DependencyInfo] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for manifest in manifests:
        path = root / manifest.path
        kind = ManifestKind(manifest.kind)
        text = read_text(path)

        if text is None:
            warnings.append(f"{manifest.path} 无法读取或不是文本文件，已跳过")
            continue

        if kind is ManifestKind.REQUIREMENTS:
            parsed = _parse_requirements(root, manifest, text)
        elif kind is ManifestKind.PYPROJECT:
            parsed, extra_warnings = _parse_pyproject(root, manifest, text)
            warnings.extend(extra_warnings)
        elif kind is ManifestKind.SETUP_PY:
            parsed = _parse_setup_py(root, manifest, text)
        elif kind is ManifestKind.ENVIRONMENT:
            parsed = _parse_environment(root, manifest, text)
        elif kind is ManifestKind.DOCKERFILE:
            parsed = _parse_dockerfile(root, manifest, text)
        else:
            continue

        for dependency in parsed:
            key = (
                canonical_name(dependency.name),
                dependency.version or "",
            )
            if key in seen:
                continue
            seen.add(key)
            dependencies.append(dependency)

            if len(dependencies) >= max_dependencies:
                warnings.append(
                    f"依赖数量超过 {max_dependencies} 项，其余已截断"
                )
                return dependencies, warnings

    return dependencies, warnings
