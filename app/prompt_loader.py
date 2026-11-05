"""Prompt template loading and rendering."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")


class PromptError(ValueError):
    """Raised when a prompt template cannot be loaded or rendered."""


class PromptLoader:
    """Load Markdown prompts from a fixed directory."""

    def __init__(self, prompt_dir: str | Path | None = None) -> None:
        self.prompt_dir = (
            Path(prompt_dir)
            if prompt_dir is not None
            else Path(__file__).resolve().parent / "prompts"
        ).resolve()

    def load(self, name: str) -> str:
        """Load one prompt by name without allowing path traversal."""
        if not name or Path(name).name != name:
            raise PromptError(f"Invalid prompt name: {name!r}")

        path = self.prompt_dir / f"{name}.md"
        if not path.is_file():
            raise PromptError(f"Prompt not found: {path}")

        return path.read_text(encoding="utf-8").strip()

    def render(self, name: str, **values: Any) -> str:
        """Render all placeholders in a prompt template."""
        template = self.load(name)
        required = set(PLACEHOLDER_PATTERN.findall(template))
        missing = sorted(required.difference(values))

        if missing:
            raise PromptError(
                f"Missing prompt values for {name}: {', '.join(missing)}"
            )

        rendered = template
        for key in required:
            rendered = rendered.replace(
                "{{" + key + "}}",
                _stringify(values[key]),
            )

        unresolved = PLACEHOLDER_PATTERN.findall(rendered)
        if unresolved:
            raise PromptError(
                f"Unresolved placeholders in {name}: "
                f"{', '.join(sorted(set(unresolved)))}"
            )

        return rendered

    def render_task(self, name: str, **values: Any) -> str:
        """Render a task prompt with the shared base rules injected."""
        if "base_rules" in values:
            raise PromptError(
                "'base_rules' is reserved and injected automatically"
            )

        return self.render(
            name,
            base_rules=self.load("base_rules"),
            **values,
        )


def _stringify(value: Any) -> str:
    """Preserve text and serialize structured values deterministically."""
    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )