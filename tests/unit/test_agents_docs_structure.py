from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
DOCS_DIR = REPO_ROOT / "docs"
PDD_MONITOR_PATH = DOCS_DIR / "pdd-monitor.md"
PRODUCTION_RULES_PATH = DOCS_DIR / "production-rules.md"
DIRECTORY_STRUCTURE_PATH = DOCS_DIR / "directory-structure.md"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
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


def validate_required_substrings(markdown: str, expected: list[str], label: str) -> None:
    missing = [item for item in expected if item not in markdown]
    if missing:
        raise ValueError(f"{label} 缺少关键内容: {', '.join(missing)}")


def test_agents_routes_all_expected_docs() -> None:
    agents_markdown = AGENTS_PATH.read_text(encoding="utf-8")
    assert len(agents_markdown.splitlines()) <= 150
    assert extract_doc_routes(agents_markdown) == {f"docs/{name}" for name in EXPECTED_DOCS}
    assert "9. **消息去重** — 所有适配器必须在处理前做 Redis 去重检查" in agents_markdown


def test_docs_exist_and_have_navigation() -> None:
    assert DOCS_DIR.is_dir()
    assert {path.name for path in DOCS_DIR.glob("*.md")} == EXPECTED_DOCS

    for path in DOCS_DIR.glob("*.md"):
        markdown = path.read_text(encoding="utf-8")
        validate_navigation(markdown)
        assert len(markdown.strip()) > len(NAVIGATION_LINE)


def test_docs_cover_new_production_and_dedupe_rules() -> None:
    pdd_monitor_markdown = PDD_MONITOR_PATH.read_text(encoding="utf-8")
    production_rules_markdown = PRODUCTION_RULES_PATH.read_text(encoding="utf-8")
    directory_structure_markdown = DIRECTORY_STRUCTURE_PATH.read_text(encoding="utf-8")
    env_example_markdown = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    validate_required_substrings(
        pdd_monitor_markdown,
        [
            "## 4.4 消息去重",
            "(shop_id + buyer_id + message_text + timestamp_10s_bucket)",
            "SHA256",
            "Redis `SET`",
            "TTL 为 600 秒",
            "存在则直接跳过",
        ],
        "docs/pdd-monitor.md",
    )
    validate_required_substrings(
        production_rules_markdown,
        [
            "## 9.4 发送频率限制",
            "reply_delay_min_ms",
            "reply_delay_max_ms",
            "asyncio.Lock",
            "## 9.5 优雅启停",
            "SIGTERM",
            "SIGINT",
            "shutdown flag",
            "最长 30 秒",
            "未完成的消息 ID",
            "## 9.6 监控告警",
            "ALERT_WEBHOOK_URL",
            "连续 3 次健康检查失败",
            "## 9.7 并发边界",
            "MAX_SHOPS",
            "错误码 `1001`",
            "150-300MB",
            "3-4GB RAM",
        ],
        "docs/production-rules.md",
    )
    validate_required_substrings(
        directory_structure_markdown,
        [
            "ShopCard.vue",
            "ShopEditDialog.vue",
            "dashboard.ts",
            "shop.ts",
            "shopConfig.ts",
        ],
        "docs/directory-structure.md",
    )
    assert "EscalationQueue.vue" not in directory_structure_markdown
    validate_required_substrings(
        env_example_markdown,
        [
            "ALERT_WEBHOOK_URL=",
            "MAX_SHOPS=10",
            "REPLY_DELAY_MIN_MS=2000",
            "REPLY_DELAY_MAX_MS=5000",
        ],
        ".env.example",
    )


def test_validate_navigation_raises_without_expected_header() -> None:
    with pytest.raises(ValueError):
        validate_navigation("# missing navigation")

    with pytest.raises(ValueError):
        validate_required_substrings("only partial content", ["missing"], "doc")
