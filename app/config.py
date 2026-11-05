"""Project-wide configuration.

Secrets are intentionally not defined here.
DeepSeek credentials are loaded by DSH from its DSH_HOME.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
JOBS_DIR = ARTIFACTS_DIR / "dsh-workspace" / "jobs"

DEFAULT_DSH_BIN = (
    ARTIFACTS_DIR
    / "dsh-runtime"
    / "node_modules"
    / ".bin"
    / "dsh.cmd"
)

DSH_BIN = Path(
    os.getenv("PAPER2RUN_DSH_BIN", str(DEFAULT_DSH_BIN))
).expanduser().resolve()

DSH_HOME = Path(
    os.getenv(
        "PAPER2RUN_DSH_HOME",
        str(ARTIFACTS_DIR / "dsh-home-sdk"),
    )
).expanduser().resolve()

DSH_PROVIDER = os.getenv("PAPER2RUN_DSH_PROVIDER", "deepseek-official")
DSH_MODEL = os.getenv("PAPER2RUN_DSH_MODEL", "deepseek-v4-flash")
DSH_PROFILE = os.getenv("PAPER2RUN_DSH_PROFILE", "sdk")
DSH_MAX_TOKENS = int(os.getenv("PAPER2RUN_DSH_MAX_TOKENS", "8192"))

REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("PAPER2RUN_REQUEST_TIMEOUT_SECONDS", "300")
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_URL = "https://api.github.com"


def ensure_runtime_directories() -> None:
    """Create runtime directories that are ignored by Git."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    DSH_HOME.mkdir(parents=True, exist_ok=True)