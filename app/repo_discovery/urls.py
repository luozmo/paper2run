"""Parsing and validation helpers for GitHub repository URLs."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_GITHUB_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,38})/"
    r"[A-Za-z0-9_.-]+(?:\.git)?(?:/[^\s<>\]\[(){}]*)?",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?\"'"
_RESERVED_REPOSITORY_NAMES = {
    "features",
    "marketplace",
    "pricing",
    "search",
    "settings",
    "site",
    "topics",
}


def canonical_github_repo_url(value: str) -> str | None:
    """Return a canonical HTTPS repository URL, or ``None`` if invalid.

    Paths below a repository (for example ``/tree/main``) are deliberately
    collapsed to their repository root.
    """
    candidate = value.strip().rstrip(_TRAILING_PUNCTUATION)
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not owner or not name:
        return None
    if owner in {".", ".."} or name in {".", ".."}:
        return None
    if owner.lower() in _RESERVED_REPOSITORY_NAMES:
        return None
    owner_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,38})"
    name_pattern = r"[A-Za-z0-9_.-]+"
    if re.fullmatch(owner_pattern, owner) is None:
        return None
    if re.fullmatch(name_pattern, name) is None:
        return None
    return f"https://github.com/{owner}/{name}"


def extract_github_repo_urls(text: str) -> list[tuple[str, str]]:
    """Extract unique canonical repository URLs and their source snippets."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in _GITHUB_URL_RE.finditer(text or ""):
        url = canonical_github_repo_url(match.group(0))
        if url is None or url.casefold() in seen:
            continue
        seen.add(url.casefold())
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        snippet = " ".join(text[start:end].split())
        results.append((url, snippet))
    return results


def split_github_repo_url(value: str) -> tuple[str, str]:
    """Return ``(owner, repository)`` for a validated GitHub URL."""
    canonical = canonical_github_repo_url(value)
    if canonical is None:
        raise ValueError(f"Not a valid GitHub repository URL: {value!r}")
    owner, name = urlsplit(canonical).path.strip("/").split("/", maxsplit=1)
    return owner, name
