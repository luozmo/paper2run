from __future__ import annotations

from pathlib import Path

import pytest

from app.prompt_loader import PromptError, PromptLoader


def test_render_task_injects_base_rules() -> None:
    loader = PromptLoader()

    rendered = loader.render_task(
        "extract_paper",
        paper_metadata={"title": "Example Paper"},
        paper_pages=[{"page_number": 1, "text": "Example text"}],
        output_schema={"type": "object"},
    )

    assert "# Paper2Run 分析规则" in rendered
    assert "Example Paper" in rendered
    assert "{{" not in rendered


def test_missing_placeholder_value_raises(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "base_rules.md").write_text("rules", encoding="utf-8")
    (prompts / "task.md").write_text(
        "{{base_rules}}\nValue: {{missing_value}}",
        encoding="utf-8",
    )

    loader = PromptLoader(prompts)

    with pytest.raises(PromptError, match="missing_value"):
        loader.render_task("task")


def test_prompt_name_rejects_path_traversal() -> None:
    loader = PromptLoader()

    with pytest.raises(PromptError, match="Invalid prompt name"):
        loader.load("../secret")


def test_structured_values_are_json_serialized(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "base_rules.md").write_text("rules", encoding="utf-8")
    (prompts / "task.md").write_text(
        "{{base_rules}}\n{{payload}}",
        encoding="utf-8",
    )

    loader = PromptLoader(prompts)
    rendered = loader.render_task("task", payload={"b": 2, "a": 1})

    assert '"a": 1' in rendered
    assert '"b": 2' in rendered