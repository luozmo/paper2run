"""GitHub-backed repository discovery for Paper2Run.

Only the public service and the small client abstraction are exported here so
the rest of the application does not depend on this module's implementation
details.
"""

from app.repo_discovery.github import (
    GitHubApiError,
    GitHubClient,
    GitHubRepository,
)
from app.repo_discovery.service import (
    GitHubRepoDiscovery,
    GitHubRepoDiscoveryService,
    RepositoryAcquisitionError,
    RepositoryDiscoveryError,
)

__all__ = [
    "GitHubApiError",
    "GitHubClient",
    "GitHubRepoDiscovery",
    "GitHubRepoDiscoveryService",
    "GitHubRepository",
    "RepositoryAcquisitionError",
    "RepositoryDiscoveryError",
]
