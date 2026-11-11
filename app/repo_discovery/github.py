"""Minimal GitHub REST API client used by repository discovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import GITHUB_API_URL, GITHUB_TOKEN


class GitHubApiError(RuntimeError):
    """Raised when GitHub cannot provide repository metadata."""


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """The GitHub fields needed by the ranker."""

    html_url: str
    owner: str
    name: str
    full_name: str
    description: str = ""
    homepage: str = ""
    topics: tuple[str, ...] = ()
    stars: int = 0
    fork: bool = False
    archived: bool = False
    api_score: float = 0.0

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> GitHubRepository:
        owner_payload = payload.get("owner")
        owner = ""
        if isinstance(owner_payload, Mapping):
            owner = str(owner_payload.get("login") or "")
        name = str(payload.get("name") or "")
        full_name = str(payload.get("full_name") or "")
        if not owner and "/" in full_name:
            owner = full_name.split("/", maxsplit=1)[0]
        if not name and "/" in full_name:
            name = full_name.split("/", maxsplit=1)[1]
        html_url = str(payload.get("html_url") or "")
        if not html_url and owner and name:
            html_url = f"https://github.com/{owner}/{name}"
        raw_topics = payload.get("topics")
        topics = (
            tuple(str(topic) for topic in raw_topics)
            if isinstance(raw_topics, list)
            else ()
        )
        return cls(
            html_url=html_url,
            owner=owner,
            name=name,
            full_name=full_name or f"{owner}/{name}",
            description=str(payload.get("description") or ""),
            homepage=str(payload.get("homepage") or ""),
            topics=topics,
            stars=int(payload.get("stargazers_count") or 0),
            fork=bool(payload.get("fork", False)),
            archived=bool(payload.get("archived", False)),
            api_score=float(payload.get("score") or 0.0),
        )


class GitHubClient:
    """Small synchronous GitHub client with injectable HTTP transport."""

    def __init__(
        self,
        *,
        token: str | None = GITHUB_TOKEN,
        api_url: str = GITHUB_API_URL,
        timeout: float = 20.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "paper2run-repo-discovery",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=api_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_repositories(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[GitHubRepository]:
        if not query.strip() or limit <= 0:
            return []
        payload = self._get_json(
            "/search/repositories",
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit, 100),
            },
        )
        items = payload.get("items")
        if not isinstance(items, list):
            raise GitHubApiError("GitHub search response did not contain an item list")
        return [
            GitHubRepository.from_api(item)
            for item in items[:limit]
            if isinstance(item, Mapping)
        ]

    def get_repository(self, owner: str, name: str) -> GitHubRepository:
        payload = self._get_json(f"/repos/{owner}/{name}")
        return GitHubRepository.from_api(payload)

    def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> Mapping[str, Any]:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GitHubApiError(f"GitHub request failed for {path}: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise GitHubApiError(f"GitHub returned an invalid response for {path}")
        return payload
