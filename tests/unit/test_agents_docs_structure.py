from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
DOCS_DIR = REPO_ROOT / "docs"
EXPECTED_DOCS = {
    "config-management.md",
    "browser-engine.md",
    "pdd-monitor.md",
    "directory-structure.md",
    "module-dev-spec.md",
    "production-rules.md",
    "testing.md",
    "coding-standards.md",
    "new-platform-checklist.md",
    "faq.md",
}
NAVIGATION_LINE = "> ← 返回 [AGENTS.md](../AGENTS.md) 查看铁律和文档路由"


def extract_doc_routes(markdown: str) -> set[str]:
    return set(re.findall(r"docs/[a-z0-9-]+\.md", markdown))


def validate_navigation(markdown: str) -> None:
    first_line = markdown.splitlines()[0] if markdown.splitlines() else ""
    if first_line != NAVIGATION_LINE:
        raise ValueError("docs 文档缺少返回 AGENTS.md 的导航行")


def test_agents_routes_all_expected_docs() -> None:
    agents_markdown = AGENTS_PATH.read_text(encoding="utf-8")
    assert len(agents_markdown.splitlines()) <= 150
    assert extract_doc_routes(agents_markdown) == {f"docs/{name}" for name in EXPECTED_DOCS}


def test_docs_exist_and_have_navigation() -> None:
    assert DOCS_DIR.is_dir()
    assert {path.name for path in DOCS_DIR.glob("*.md")} == EXPECTED_DOCS

    for path in DOCS_DIR.glob("*.md"):
        markdown = path.read_text(encoding="utf-8")
        validate_navigation(markdown)
        assert len(markdown.strip()) > len(NAVIGATION_LINE)


def test_validate_navigation_raises_without_expected_header() -> None:
    with pytest.raises(ValueError):
        validate_navigation("# missing navigation")
