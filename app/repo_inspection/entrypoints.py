"""Detect runnable entry points and documented run commands."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.models import Evidence, EvidenceKind, RepositoryEntryPoint
from app.repo_inspection.files import (
    line_locator,
    read_text,
    relative_locator,
)
from app.repo_inspection.manifests import SKIP_DIRECTORIES

README_NAMES = (
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme.markdown",
    "readme",
)

DEFAULT_MAX_ENTRY_POINTS = 20
DEFAULT_MAX_RUN_COMMANDS = 20

ENTRY_STEM_PATTERN = re.compile(
    r"(^|_)(train|main|run|eval|evaluate|evaluation|inference|infer|"
    r"predict|finetune|fine_tune|demo|app|serve|server|launch|generate|"
    r"sample|synthesize|convert)(_|$)",
    re.IGNORECASE,
)

RUN_COMMAND_PATTERN = re.compile(
    r"^(?:[$>%]\s*)?(?:PS\s+[^>]*>\s*)?"
    r"(python[0-9.]*|pip[0-9.]*|pip3|torchrun|accelerate|deepspeed|"
    r"bash|sh|conda|make|docker|uv|poetry)\b",
    re.IGNORECASE,
)

UNSAFE_COMMAND_PATTERN = re.compile(
    r"(^|\s)(sudo\s|rm\s+-|mkfs|dd\s+if=|"
    r"curl[^\n]*\|\s*(?:sh|bash)|wget[^\n]*\|\s*(?:sh|bash)|"
    r"chmod\s+777|>\s*/dev/sd)",
    re.IGNORECASE,
)

MAIN_GUARD_PATTERN = re.compile(r"__name__\s*==\s*['\"]__main__['\"]")


def find_readme(root: Path) -> Path | None:
    """Return the repository-level README when present."""

    root = Path(root)
    for name in README_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate

    try:
        entries = sorted(root.iterdir())
    except OSError:
        return None

    for entry in entries:
        if entry.is_file() and entry.name.lower().startswith("readme"):
            return entry

    return None


def _strip_prompt(line: str) -> str:
    stripped = line.strip()
    for prefix in ("$ ", "> ", "% "):
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return re.sub(r"^PS\s+[^>]*>\s*", "", stripped).strip()


def extract_run_commands(
    text: str,
    *,
    max_commands: int = DEFAULT_MAX_RUN_COMMANDS,
) -> list[tuple[int, str]]:
    """Collect ``(line_number, command)`` pairs from README content.

    Destructive shell snippets are dropped instead of being reported.
    """

    commands: list[tuple[int, str]] = []
    seen: set[str] = set()

    for number, raw in enumerate(text.splitlines(), 1):
        command = _strip_prompt(raw)
        if not command or command.startswith("#"):
            continue
        if RUN_COMMAND_PATTERN.match(command) is None:
            continue
        if UNSAFE_COMMAND_PATTERN.search(command):
            continue
        if command in seen:
            continue

        seen.add(command)
        commands.append((number, command))

        if len(commands) >= max_commands:
            break

    return commands


SCRIPT_SKIP_DIRECTORIES = SKIP_DIRECTORIES | {
    "test",
    "tests",
    "benchmark",
    "benchmarks",
    "e2e",
    "ci",
    "thirdparty",
    "venv",
}

ENTRY_STEM_BLOCKLIST = re.compile(
    r"(^|_)(lint|check|checks|test|tests|conftest)(_|$)",
    re.IGNORECASE,
)

DEFAULT_SCRIPT_DEPTH = 2
MAX_SCRIPT_CANDIDATES = 50


def _iter_script_paths(
    root: Path, *, max_depth: int = DEFAULT_SCRIPT_DEPTH
) -> list[Path]:
    """Find shallow Python scripts whose names look like entry points."""

    root = Path(root)
    if not root.is_dir():
        return []

    base_depth = len(root.resolve().parts)
    candidates: list[Path] = []

    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.resolve().parts) - base_depth

        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and name.lower() not in SCRIPT_SKIP_DIRECTORIES
        )
        if depth >= max_depth:
            dirnames[:] = []

        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue

            stem = filename[: -len(".py")]
            if ENTRY_STEM_PATTERN.search(stem) is None:
                continue
            if ENTRY_STEM_BLOCKLIST.search(stem) is not None:
                continue

            candidates.append(current_path / filename)
            if len(candidates) >= MAX_SCRIPT_CANDIDATES:
                return candidates

    return candidates


def find_entry_points(
    root: Path,
    *,
    documented_commands: list[tuple[int, str]] | None = None,
    readme_path: Path | None = None,
    max_entry_points: int = DEFAULT_MAX_ENTRY_POINTS,
) -> list[RepositoryEntryPoint]:
    """Match Python scripts with the commands documented in the README."""

    root = Path(root)
    documented = documented_commands or []
    entry_points: list[RepositoryEntryPoint] = []

    for script in _iter_script_paths(root):
        if ENTRY_STEM_PATTERN.search(script.stem) is None:
            continue

        relative = relative_locator(root, script)
        text = read_text(script, max_bytes=64 * 1024) or ""
        evidence: list[Evidence] = []
        command: str | None = None
        confidence = 0.3

        for number, documented_command in documented:
            if script.name in documented_command:
                command = documented_command
                confidence = 0.9
                if readme_path is not None:
                    evidence.append(
                        Evidence(
                            kind=EvidenceKind.REPO_FILE,
                            locator=line_locator(
                                root, readme_path, number
                            ),
                            quote=documented_command,
                            confidence=0.9,
                        )
                    )
                break

        if command is None and MAIN_GUARD_PATTERN.search(text):
            command = f"python {relative}"
            confidence = 0.6

        evidence.append(
            Evidence(
                kind=EvidenceKind.REPO_FILE,
                locator=relative,
                confidence=confidence,
            )
        )

        entry_points.append(
            RepositoryEntryPoint(
                path=relative,
                command=command,
                evidence=evidence,
                confidence=confidence,
            )
        )

        if len(entry_points) >= max_entry_points:
            break

    return entry_points
