"""Defensive file-reading helpers shared by repository inspection."""

from __future__ import annotations

from pathlib import Path

MAX_TEXT_BYTES = 512 * 1024
BINARY_PROBE_BYTES = 4096


def read_text(path: Path, *, max_bytes: int = MAX_TEXT_BYTES) -> str | None:
    """Return decoded text, or ``None`` when unreadable or binary.

    Never raises: inspection must degrade into warnings instead of
    crashing the whole pipeline on one odd file.
    """

    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        return None

    if b"\x00" in raw[:BINARY_PROBE_BYTES]:
        return None

    return raw.decode("utf-8", errors="replace")


def relative_locator(root: Path, path: Path) -> str:
    """Return a stable POSIX-style path relative to ``root``."""

    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        relative = path
    return relative.as_posix()


def line_locator(root: Path, path: Path, line_number: int) -> str:
    """Return ``relative/path:line`` for an evidence reference."""

    return f"{relative_locator(root, path)}:{line_number}"
