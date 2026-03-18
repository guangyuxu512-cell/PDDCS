from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
ROUTER_PATH = FRONTEND_DIR / "src" / "router" / "index.ts"
REQUEST_PATH = FRONTEND_DIR / "src" / "api" / "request.ts"
VITE_CONFIG_PATH = FRONTEND_DIR / "vite.config.ts"
ENV_PATH = FRONTEND_DIR / ".env.development"

EXPECTED_FILES = {
    "package.json",
    "index.html",
    "tsconfig.json",
    "vite.config.ts",
    ".env.development",
    "src/main.ts",
    "src/App.vue",
    "src/env.d.ts",
    "src/style.css",
    "src/api/request.ts",
    "src/router/index.ts",
    "src/types/api.ts",
    "src/components/layout/AppLayout.vue",
    "src/components/layout/Sidebar.vue",
    "src/components/layout/Topbar.vue",
    "src/views/Dashboard.vue",
    "src/views/ShopManage.vue",
    "src/views/ShopEdit.vue",
    "src/views/ChatMonitor.vue",
    "src/views/KnowledgeBase.vue",
    "src/views/EscalationQueue.vue",
    "src/views/Settings.vue",
    "src/mock/index.ts",
    "src/mock/dashboard.ts",
}
EXPECTED_ROUTE_PATHS = [
    "/",
    "/dashboard",
    "/shops",
    "/shops/edit/:id?",
    "/chat",
    "/knowledge",
    "/escalation",
    "/settings",
]


def validate_required_substrings(content: str, required_substrings: list[str], label: str) -> None:
    missing = [item for item in required_substrings if item not in content]
    if missing:
        raise ValueError(f"{label} 缺少关键内容: {', '.join(missing)}")


def extract_route_paths(router_content: str) -> list[str]:
    paths: list[str] = []
    for segment in router_content.split("path: '")[1:]:
        paths.append(segment.split("'", 1)[0])
    return paths


def validate_route_paths(paths: list[str]) -> None:
    if paths != EXPECTED_ROUTE_PATHS:
        raise ValueError("路由表与 Step 1 要求不一致")


def test_frontend_step1_required_files_exist() -> None:
    assert FRONTEND_DIR.is_dir()

    existing = {
        str(path.relative_to(FRONTEND_DIR)).replace("\\", "/")
        for path in FRONTEND_DIR.rglob("*")
        if path.is_file()
    }
    assert EXPECTED_FILES.issubset(existing)
    assert ENV_PATH.read_text(encoding="utf-8").strip() == "VITE_API_BASE_URL=/api"


def test_frontend_router_request_and_vite_config_match_step1_contract() -> None:
    router_content = ROUTER_PATH.read_text(encoding="utf-8")
    request_content = REQUEST_PATH.read_text(encoding="utf-8")
    vite_config_content = VITE_CONFIG_PATH.read_text(encoding="utf-8")

    validate_route_paths(extract_route_paths(router_content))
    validate_required_substrings(
        request_content,
        [
            "import.meta.env.VITE_API_BASE_URL",
            "axios.create",
            "response.data.code !== 0",
            "unwrapResponse",
        ],
        "request.ts",
    )
    validate_required_substrings(
        vite_config_content,
        [
            "AutoImport(",
            "Components(",
            "ElementPlusResolver()",
            "viteMockServe(",
            "mockPath: 'src/mock'",
        ],
        "vite.config.ts",
    )


def test_validation_helpers_raise_for_missing_contract() -> None:
    with pytest.raises(ValueError):
        validate_route_paths(["/dashboard"])

    with pytest.raises(ValueError):
        validate_required_substrings("axios.create()", ["import.meta.env.VITE_API_BASE_URL"], "request.ts")
