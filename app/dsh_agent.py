"""DSH-backed paper analysis agent."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepseek_harness import DeepSeekHarness

from app.config import (
    DSH_BIN,
    DSH_HOME,
    DSH_MAX_TOKENS,
    DSH_MODEL,
    DSH_PROFILE,
    DSH_PROVIDER,
    JOBS_DIR,
)
from app.models import PaperReport
from app.pdf_loader import load_pdf
from app.prompt_loader import PromptLoader

Runner = Callable[[str, Path, str], str]
SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class DshAgentError(RuntimeError):
    """Raised when DSH cannot complete or return a valid report."""


class PaperAnalysisAgent:
    """Run paper extraction through DeepSeek Harness."""

    def __init__(
        self,
        *,
        model: str = DSH_MODEL,
        provider: str = DSH_PROVIDER,
        profile: str = DSH_PROFILE,
        dsh_bin: Path = DSH_BIN,
        dsh_home: Path = DSH_HOME,
        max_tokens: int = DSH_MAX_TOKENS,
        job_root: Path = JOBS_DIR,
        prompt_loader: PromptLoader | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.profile = profile
        self.dsh_bin = Path(dsh_bin).resolve()
        self.dsh_home = Path(dsh_home).resolve()
        self.max_tokens = max_tokens
        self.job_root = Path(job_root).resolve()
        self.prompt_loader = prompt_loader or PromptLoader()
        self._runner = runner or self._run_dsh

    def analyze_pdf(
        self,
        pdf_path: str | Path,
        *,
        job_id: str | None = None,
        session_id: str | None = None,
    ) -> PaperReport:
        """Extract a PaperReport from one PDF."""
        job = job_id or f"paper-{uuid.uuid4().hex[:12]}"
        self._validate_job_id(job)

        workspace = self.job_root / job / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        pdf = load_pdf(pdf_path)
        paper_text_path = workspace / "paper_text.json"
        paper_text_path.write_text(
            pdf.model_dump_json(indent=2),
            encoding="utf-8",
        )

        prompt = self.prompt_loader.render_task(
            "extract_paper",
            paper_metadata=pdf.metadata,
            paper_pages=[
                page.model_dump(mode="json") for page in pdf.pages
            ],
            output_schema=PaperReport.model_json_schema(),
        )
        (workspace / "prompt.md").write_text(prompt, encoding="utf-8")

        response = self._runner(
            prompt,
            workspace,
            session_id or job,
        )
        payload = extract_json_object(response)
        report = PaperReport.model_validate(payload)

        (workspace / "result.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _run_dsh(self, prompt: str, workspace: Path, session_id: str) -> str:
        """Execute one prompt through the configured DSH profile."""
        with DeepSeekHarness(
            provider=self.provider,
            model=self.model,
            max_tokens=self.max_tokens,
            cwd=str(workspace),
            dsh_home=str(self.dsh_home),
            dsh_bin=str(self.dsh_bin),
            profile=self.profile,
        ) as harness:
            result = harness.run(prompt, session_id=session_id)

        if result.finish_reason != "completed":
            raise DshAgentError(
                f"DSH did not complete: {result.finish_reason}"
            )

        if not result.final_response.strip():
            raise DshAgentError("DSH returned an empty response")

        return result.final_response

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not SAFE_JOB_ID.fullmatch(job_id):
            raise ValueError(
                "job_id may only contain letters, digits, '.', '_' and '-'"
            )


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object from a model response."""
    start = text.find("{")
    if start < 0:
        raise DshAgentError("No JSON object found in DSH response")

    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise DshAgentError(f"Invalid JSON returned by DSH: {exc}") from exc

    if not isinstance(value, dict):
        raise DshAgentError("DSH response JSON must be an object")

    return value