"""Repository discovery service implementation."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.models import (
    Evidence,
    EvidenceKind,
    PaperMetadata,
    RepoCandidate,
    RepoOfficialStatus,
)
from app.repo_discovery.github import (
    GitHubApiError,
    GitHubClient,
    GitHubRepository,
)
from app.repo_discovery.ranking import RankedRepository, rank_repository
from app.repo_discovery.urls import (
    canonical_github_repo_url,
    extract_github_repo_urls,
    split_github_repo_url,
)


class RepositoryDiscoveryError(RuntimeError):
    """Raised when discovery fails before any candidates can be produced."""


class RepositoryAcquisitionError(RuntimeError):
    """Raised when a repository cannot be cloned safely."""


class DiscoveryClient(Protocol):
    def search_repositories(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[GitHubRepository]: ...

    def get_repository(self, owner: str, name: str) -> GitHubRepository: ...


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class GitHubRepoDiscovery:
    """Discover, rank, and clone GitHub repositories for one paper."""

    def __init__(
        self,
        *,
        client: DiscoveryClient | None = None,
        repository_root: Path | None = None,
        search_limit: int = 10,
        max_candidates: int = 10,
        clone_timeout: float = 300.0,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        if search_limit < 1 or max_candidates < 1:
            raise ValueError("search_limit and max_candidates must be positive")
        self.client = client or GitHubClient()
        self.repository_root = (
            Path(repository_root)
            if repository_root is not None
            else Path(tempfile.gettempdir()) / "paper2run-repositories"
        )
        self.search_limit = search_limit
        self.max_candidates = max_candidates
        self.clone_timeout = clone_timeout
        self._command_runner = command_runner

    def discover(
        self,
        *,
        paper: PaperMetadata,
        paper_text: str,
    ) -> list[RepoCandidate]:
        """Find candidates from paper links and GitHub repository search.

        Direct links remain available even if GitHub's API is unavailable. API
        failures are otherwise reported only when no candidate can be formed.
        """
        evidence_text = [
            value
            for item in paper.evidence
            for value in (item.url, item.quote)
            if value
        ]
        direct_links = extract_github_repo_urls(
            "\n".join(
                value for value in (paper.url, *evidence_text, paper_text) if value
            )
        )
        direct_snippets = {url.casefold(): snippet for url, snippet in direct_links}
        repositories: dict[str, GitHubRepository] = {}
        api_errors: list[str] = []

        for url, _snippet in direct_links:
            owner, name = split_github_repo_url(url)
            try:
                repository = self._coerce_repository(
                    self.client.get_repository(owner, name)
                )
            except GitHubApiError as exc:
                api_errors.append(str(exc))
                repository = GitHubRepository(
                    html_url=url,
                    owner=owner,
                    name=name,
                    full_name=f"{owner}/{name}",
                )
            repositories[url.casefold()] = repository

        for query in self._build_search_queries(paper):
            try:
                found = self.client.search_repositories(
                    query,
                    limit=self.search_limit,
                )
            except GitHubApiError as exc:
                api_errors.append(str(exc))
                continue
            for raw_repository in found:
                repository = self._coerce_repository(raw_repository)
                url = canonical_github_repo_url(repository.html_url)
                if url is not None:
                    repositories.setdefault(url.casefold(), repository)

        if not repositories and api_errors:
            raise RepositoryDiscoveryError("; ".join(dict.fromkeys(api_errors)))

        candidates: list[tuple[RankedRepository, RepoCandidate]] = []
        for key, repository in repositories.items():
            url = canonical_github_repo_url(repository.html_url)
            if url is None:
                continue
            explicit = key in direct_snippets
            ranked = rank_repository(
                paper,
                repository,
                explicit_in_paper=explicit,
            )
            evidence = self._candidate_evidence(
                repository=repository,
                explicit_snippet=direct_snippets.get(key),
            )
            candidate = RepoCandidate(
                url=url,
                owner=repository.owner,
                name=repository.name,
                official_status=ranked.status,
                confidence=ranked.confidence,
                evidence=evidence,
                notes="; ".join(ranked.reasons) or None,
            )
            candidates.append((ranked, candidate))

        status_priority = {
            RepoOfficialStatus.OFFICIAL: 3,
            RepoOfficialStatus.LIKELY_OFFICIAL: 2,
            RepoOfficialStatus.UNKNOWN: 1,
            RepoOfficialStatus.THIRD_PARTY: 0,
        }
        candidates.sort(
            key=lambda item: (
                -status_priority[item[0].status],
                -item[1].confidence,
                -item[0].title_similarity,
                item[1].url.casefold(),
            )
        )
        return [candidate for _, candidate in candidates[: self.max_candidates]]

    def acquire(self, *, repo_url: str) -> Path:
        """Clone a validated GitHub repository into the configured cache root."""
        canonical = canonical_github_repo_url(repo_url)
        if canonical is None:
            raise RepositoryAcquisitionError(
                "Only valid github.com repository URLs can be acquired"
            )
        owner, name = split_github_repo_url(canonical)
        self.repository_root.mkdir(parents=True, exist_ok=True)
        root = self.repository_root.resolve()
        destination = (root / f"{owner}--{name}").resolve()
        if root not in destination.parents:
            raise RepositoryAcquisitionError("Unsafe repository destination")

        if destination.exists():
            if (destination / ".git").is_dir():
                return destination
            raise RepositoryAcquisitionError(
                f"Clone destination already exists and is not a Git repository: {destination}"
            )

        command = [
            "git",
            "-c",
            "http.version=HTTP/1.1",
            "clone",
            "--depth",
            "1",
            "--",
            f"{canonical}.git",
            str(destination),
        ]
        try:
            result = self._command_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._remove_partial_clone(destination)
            raise RepositoryAcquisitionError(f"Unable to run git clone: {exc}") from exc
        if result.returncode != 0:
            self._remove_partial_clone(destination)
            detail = (result.stderr or result.stdout or "unknown Git error").strip()
            raise RepositoryAcquisitionError(f"git clone failed: {detail}")
        if not (destination / ".git").is_dir():
            self._remove_partial_clone(destination)
            raise RepositoryAcquisitionError(
                "git clone completed without a Git repository"
            )
        return destination

    @staticmethod
    def _build_search_queries(paper: PaperMetadata) -> list[str]:
        queries: list[str] = []
        title = " ".join(paper.title.split())
        if title:
            safe_title = title.replace('"', " ")[:180]
            queries.append(f'"{safe_title}" in:name,description,readme')
        if paper.doi:
            safe_doi = re.sub(r"\s+", "", paper.doi)[:180]
            if safe_doi:
                queries.append(f'"{safe_doi}" in:readme')
        title_terms = [
            term for term in re.findall(r"[A-Za-z0-9]+", title) if len(term) >= 4
        ][:4]
        if paper.authors and title_terms:
            author_parts = re.findall(r"[A-Za-z0-9]+", paper.authors[0])
            if author_parts:
                author = author_parts[-1][:80]
                terms = " ".join(title_terms)
                queries.append(f'"{author}" {terms} in:name,description,readme')
        return list(dict.fromkeys(queries))

    @staticmethod
    def _candidate_evidence(
        *,
        repository: GitHubRepository,
        explicit_snippet: str | None,
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        if explicit_snippet is not None:
            evidence.append(
                Evidence(
                    kind=EvidenceKind.PAPER,
                    locator="paper text: GitHub repository URL",
                    quote=explicit_snippet or repository.html_url,
                    url=repository.html_url,
                    confidence=0.98,
                )
            )
        metadata_quote = repository.description.strip()
        evidence.append(
            Evidence(
                kind=EvidenceKind.WEB,
                locator=f"GitHub repository metadata: {repository.full_name}",
                quote=metadata_quote or None,
                url=repository.html_url,
                confidence=0.8 if metadata_quote else 0.65,
            )
        )
        return evidence

    @staticmethod
    def _coerce_repository(value: Any) -> GitHubRepository:
        if isinstance(value, GitHubRepository):
            return value
        if isinstance(value, Mapping):
            return GitHubRepository.from_api(value)
        raise RepositoryDiscoveryError(
            f"Discovery client returned an unsupported value: {type(value).__name__}"
        )

    @staticmethod
    def _remove_partial_clone(destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)


# Descriptive alias retained for callers that prefer the protocol's naming.
GitHubRepoDiscoveryService = GitHubRepoDiscovery
