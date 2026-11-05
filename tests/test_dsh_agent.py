from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from app.dsh_agent import DshAgentError, PaperAnalysisAgent
from app.prompt_loader import PromptLoader


def _create_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "We train with batch size 256 on 8 V100 GPUs.",
    )
    document.save(path)
    document.close()


def test_analyze_pdf_uses_prompt_and_writes_results(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    _create_pdf(pdf_path)

    captured: dict[str, str] = {}

    def fake_runner(
        prompt: str,
        workspace: Path,
        session_id: str,
    ) -> str:
        captured["prompt"] = prompt
        captured["workspace"] = str(workspace)
        captured["session_id"] = session_id

        return """```json
{
  "paper": {
    "title": "Example Paper",
    "authors": [],
    "evidence": []
  },
  "code_availability": "uncertain",
  "repo_candidates": [],
  "selected_repo_url": null,
  "dependencies": [],
  "experiment_parameters": [],
  "missing_items": [],
  "warnings": [],
  "generated_at": "2026-11-05T00:00:00Z"
}
```"""

    agent = PaperAnalysisAgent(
        job_root=tmp_path / "jobs",
        prompt_loader=PromptLoader(),
        runner=fake_runner,
    )

    report = agent.analyze_pdf(pdf_path, job_id="job-001")

    workspace = tmp_path / "jobs" / "job-001" / "workspace"

    assert report.paper.title == "Example Paper"
    assert report.code_availability == "uncertain"
    assert "# Paper2Run 分析规则" in captured["prompt"]
    assert "batch size 256" in captured["prompt"]
    assert captured["session_id"] == "job-001"
    assert captured["workspace"] == str(workspace)
    assert (workspace / "paper_text.json").is_file()
    assert (workspace / "prompt.md").is_file()
    assert (workspace / "result.json").is_file()


def test_invalid_json_raises_dsh_agent_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    _create_pdf(pdf_path)

    def invalid_runner(
        prompt: str,
        workspace: Path,
        session_id: str,
    ) -> str:
        return "not valid json"

    agent = PaperAnalysisAgent(
        job_root=tmp_path / "jobs",
        runner=invalid_runner,
    )

    with pytest.raises(DshAgentError, match="No JSON object"):
        agent.analyze_pdf(pdf_path, job_id="job-002")


def test_unsafe_job_id_is_rejected(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    _create_pdf(pdf_path)

    agent = PaperAnalysisAgent(
        job_root=tmp_path / "jobs",
        runner=lambda prompt, workspace, session_id: json.dumps(
            {"paper": {"title": "Unused"}}
        ),
    )

    with pytest.raises(ValueError, match="job_id"):
        agent.analyze_pdf(pdf_path, job_id="../escape")