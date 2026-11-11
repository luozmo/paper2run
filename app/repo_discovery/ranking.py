"""Evidence-based scoring and classification of repository candidates."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from app.models import PaperMetadata, RepoOfficialStatus
from app.repo_discovery.github import GitHubRepository

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "using",
    "via",
    "with",
}
_OFFICIAL_MARKERS = (
    "official implementation",
    "official code",
    "official repository",
    "authors' implementation",
    "author implementation",
)
_THIRD_PARTY_MARKERS = (
    "unofficial",
    "reimplementation",
    "re-implementation",
    "reproduction",
    "replication",
    "paper reproduction",
)


@dataclass(frozen=True, slots=True)
class RankedRepository:
    repository: GitHubRepository
    status: RepoOfficialStatus
    confidence: float
    title_similarity: float
    author_match: bool
    reasons: tuple[str, ...]


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.casefold())
    return {word for word in words if len(word) > 1 and word not in _STOP_WORDS}


def title_similarity(title: str, repository: GitHubRepository) -> float:
    paper_tokens = _tokens(title)
    repo_tokens = _tokens(
        " ".join((repository.name, repository.description, " ".join(repository.topics)))
    )
    if not paper_tokens or not repo_tokens:
        return 0.0
    overlap = len(paper_tokens & repo_tokens)
    coverage = overlap / len(paper_tokens)
    jaccard = overlap / len(paper_tokens | repo_tokens)
    exact_name = _normalise(title) == _normalise(repository.name)
    return min(1.0, 0.65 * coverage + 0.25 * jaccard + (0.1 if exact_name else 0.0))


def owner_matches_authors(owner: str, authors: list[str]) -> bool:
    normalised_owner = _normalise(owner)
    if not normalised_owner:
        return False
    for author in authors:
        parts = [_normalise(part) for part in re.findall(r"[\w'-]+", author)]
        parts = [part for part in parts if part]
        if not parts:
            continue
        candidates = {"".join(parts), parts[-1]}
        if len(parts) > 1:
            candidates.add(parts[0] + parts[-1])
            candidates.add(parts[-1] + parts[0])
        if any(
            candidate
            and (
                candidate == normalised_owner
                or (len(candidate) >= 4 and candidate in normalised_owner)
            )
            for candidate in candidates
        ):
            return True
    return False


def rank_repository(
    paper: PaperMetadata,
    repository: GitHubRepository,
    *,
    explicit_in_paper: bool = False,
) -> RankedRepository:
    """Classify a repository using conservative, explainable heuristics."""
    similarity = title_similarity(paper.title, repository)
    author_match = owner_matches_authors(repository.owner, paper.authors)
    searchable = " ".join(
        (
            repository.name,
            repository.description,
            repository.homepage,
            " ".join(repository.topics),
        )
    ).casefold()
    official_marker = any(marker in searchable for marker in _OFFICIAL_MARKERS)
    third_party_marker = any(marker in searchable for marker in _THIRD_PARTY_MARKERS)
    reasons: list[str] = []

    if explicit_in_paper:
        status = RepoOfficialStatus.OFFICIAL
        confidence = 0.98
        reasons.append("repository URL appears explicitly in the paper")
    elif third_party_marker or repository.fork:
        status = RepoOfficialStatus.THIRD_PARTY
        confidence = 0.82 if third_party_marker else 0.72
        reasons.append(
            "repository identifies as a reproduction"
            if third_party_marker
            else "repository is a fork"
        )
    elif official_marker and similarity >= 0.25:
        status = RepoOfficialStatus.LIKELY_OFFICIAL
        confidence = 0.84
        reasons.append("repository metadata claims an official implementation")
    elif author_match and similarity >= 0.35:
        status = RepoOfficialStatus.LIKELY_OFFICIAL
        confidence = min(0.92, 0.68 + 0.24 * similarity)
        reasons.append("repository owner matches a paper author")
    else:
        status = RepoOfficialStatus.UNKNOWN
        confidence = min(0.74, 0.18 + 0.5 * similarity)

    if similarity > 0:
        reasons.append(f"paper-title similarity={similarity:.2f}")
    if repository.archived:
        confidence = max(0.0, confidence - 0.08)
        reasons.append("repository is archived")
    if repository.stars > 0:
        # Stars are a weak tie-breaker, never evidence of official ownership.
        confidence = min(
            0.99, confidence + min(0.025, math.log10(repository.stars + 1) / 160)
        )

    return RankedRepository(
        repository=repository,
        status=status,
        confidence=round(confidence, 4),
        title_similarity=similarity,
        author_match=author_match,
        reasons=tuple(reasons),
    )
