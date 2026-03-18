from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
ROUTER_PATH = FRONTEND_DIR / "src" / "router" / "index.ts"
REQUEST_PATH = FRONTEND_DIR / "src" / "api" / "request.ts"
API_DASHBOARD_PATH = FRONTEND_DIR / "src" / "api" / "dashboard.ts"
API_SHOP_PATH = FRONTEND_DIR / "src" / "api" / "shop.ts"
API_SHOP_CONFIG_PATH = FRONTEND_DIR / "src" / "api" / "shopConfig.ts"
TYPE_DASHBOARD_PATH = FRONTEND_DIR / "src" / "types" / "dashboard.ts"
TYPE_SHOP_PATH = FRONTEND_DIR / "src" / "types" / "shop.ts"
TYPE_SHOP_CONFIG_PATH = FRONTEND_DIR / "src" / "types" / "shopConfig.ts"
MOCK_DASHBOARD_PATH = FRONTEND_DIR / "src" / "mock" / "dashboard.ts"
MOCK_SHOP_PATH = FRONTEND_DIR / "src" / "mock" / "shop.ts"
MOCK_SHOP_CONFIG_PATH = FRONTEND_DIR / "src" / "mock" / "shopConfig.ts"
DASHBOARD_MOCK_INDEX_PATH = FRONTEND_DIR / "src" / "mock" / "index.ts"
DASHBOARD_VIEW_PATH = FRONTEND_DIR / "src" / "views" / "Dashboard.vue"
SHOP_MANAGE_VIEW_PATH = FRONTEND_DIR / "src" / "views" / "ShopManage.vue"
SHOP_CARD_PATH = FRONTEND_DIR / "src" / "components" / "ShopCard.vue"
SHOP_EDIT_DIALOG_PATH = FRONTEND_DIR / "src" / "components" / "ShopEditDialog.vue"
APP_LAYOUT_PATH = FRONTEND_DIR / "src" / "components" / "layout" / "AppLayout.vue"
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
    "src/api/dashboard.ts",
    "src/api/shop.ts",
    "src/api/shopConfig.ts",
    "src/router/index.ts",
    "src/types/api.ts",
    "src/types/dashboard.ts",
    "src/types/shop.ts",
    "src/types/shopConfig.ts",
    "src/components/ShopCard.vue",
    "src/components/ShopEditDialog.vue",
    "src/components/layout/AppLayout.vue",
    "src/components/layout/Sidebar.vue",
    "src/views/Dashboard.vue",
    "src/views/ShopManage.vue",
    "src/views/ShopEdit.vue",
    "src/views/ChatMonitor.vue",
    "src/views/KnowledgeBase.vue",
    "src/views/Settings.vue",
    "src/mock/index.ts",
    "src/mock/dashboard.ts",
    "src/mock/shop.ts",
    "src/mock/shopConfig.ts",
}
EXPECTED_ROUTE_PATHS = [
    "/",
    "/dashboard",
    "/shops",
    "/shops/edit/:id?",
    "/chat",
    "/knowledge",
    "/settings",
]


def validate_required_substrings(content: str, required_substrings: list[str], label: str) -> None:
    missing = [item for item in required_substrings if item not in content]
    if missing:
        raise ValueError(f"{label} 缺少关键内容: {', '.join(missing)}")


def validate_forbidden_substrings(content: str, forbidden_substrings: list[str], label: str) -> None:
    existing = [item for item in forbidden_substrings if item in content]
    if existing:
        raise ValueError(f"{label} 不应包含: {', '.join(existing)}")


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
    assert "src/views/EscalationQueue.vue" not in existing
    assert "src/components/layout/Topbar.vue" not in existing
    assert ENV_PATH.read_text(encoding="utf-8").strip() == "VITE_API_BASE_URL=http://localhost:8000/api"


def test_frontend_router_request_and_vite_config_match_step1_contract() -> None:
    router_content = ROUTER_PATH.read_text(encoding="utf-8")
    request_content = REQUEST_PATH.read_text(encoding="utf-8")
    dashboard_api_content = API_DASHBOARD_PATH.read_text(encoding="utf-8")
    shop_api_content = API_SHOP_PATH.read_text(encoding="utf-8")
    shop_config_api_content = API_SHOP_CONFIG_PATH.read_text(encoding="utf-8")
    dashboard_type_content = TYPE_DASHBOARD_PATH.read_text(encoding="utf-8")
    shop_type_content = TYPE_SHOP_PATH.read_text(encoding="utf-8")
    shop_config_type_content = TYPE_SHOP_CONFIG_PATH.read_text(encoding="utf-8")
    dashboard_mock_content = MOCK_DASHBOARD_PATH.read_text(encoding="utf-8")
    shop_mock_content = MOCK_SHOP_PATH.read_text(encoding="utf-8")
    shop_config_mock_content = MOCK_SHOP_CONFIG_PATH.read_text(encoding="utf-8")
    mock_index_content = DASHBOARD_MOCK_INDEX_PATH.read_text(encoding="utf-8")
    dashboard_view_content = DASHBOARD_VIEW_PATH.read_text(encoding="utf-8")
    shop_manage_view_content = SHOP_MANAGE_VIEW_PATH.read_text(encoding="utf-8")
    shop_card_content = SHOP_CARD_PATH.read_text(encoding="utf-8")
    shop_edit_dialog_content = SHOP_EDIT_DIALOG_PATH.read_text(encoding="utf-8")
    app_layout_content = APP_LAYOUT_PATH.read_text(encoding="utf-8")
    vite_config_content = VITE_CONFIG_PATH.read_text(encoding="utf-8")
    sidebar_content = (FRONTEND_DIR / "src" / "components" / "layout" / "Sidebar.vue").read_text(
        encoding="utf-8"
    )

    validate_route_paths(extract_route_paths(router_content))
    validate_forbidden_substrings(
        router_content,
        ["Bell", "/escalation", "EscalationQueue.vue"],
        "router/index.ts",
    )
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
        dashboard_api_content,
        [
            "fetchDashboardSummary",
            "unwrapResponse",
            "request.get<ApiResponse<DashboardSummary>>('/dashboard/summary')",
        ],
        "api/dashboard.ts",
    )
    validate_required_substrings(
        shop_api_content,
        [
            "fetchShopList",
            "toggleShopAi",
            "toggleShopStatus",
            "request.get<ApiResponse<Shop[]>>('/shops')",
            "request.patch<ApiResponse<Shop>>(`/shops/${shopId}/ai`, { enabled })",
            "request.post<ApiResponse<Shop>>(`/shops/${shopId}/toggle`)",
        ],
        "api/shop.ts",
    )
    validate_required_substrings(
        shop_config_api_content,
        [
            "fetchShopConfig",
            "saveShopConfig",
            "request.get<ApiResponse<ShopConfig>>(`/shops/${shopId}/config`)",
            "request.put<ApiResponse<ShopConfig>>(`/shops/${shopId}/config`, config)",
        ],
        "api/shopConfig.ts",
    )
    validate_required_substrings(
        dashboard_type_content,
        [
            "export interface DashboardSummary",
            "todayServedCount: number",
            "aiReplyRate: number",
            "escalationCount: number",
            "avgFirstResponseMs: number",
            "unrepliedCount: number",
            "yesterdayServedCount: number",
        ],
        "types/dashboard.ts",
    )
    validate_required_substrings(
        shop_type_content,
        [
            "export type Platform = 'pdd' | 'douyin' | 'qianniu';",
            "export interface Shop",
            "id: string;",
            "isOnline: boolean;",
            "aiEnabled: boolean;",
            "todayServedCount: number;",
            "lastActiveAt: string;",
            "cookieValid: boolean;",
            "export const platformLabel: Record<Platform, string>",
        ],
        "types/shop.ts",
    )
    validate_required_substrings(
        shop_config_type_content,
        [
            "export type EscalationRuleType = 'keyword' | 'repeat_ask' | 'order_amount' | 'regex';",
            "export interface EscalationRule",
            "export interface ShopConfig",
            "cookieLastRefresh: string;",
            "llmMode: 'global' | 'custom';",
            "humanAgentName: string;",
            "escalationRules: EscalationRule[];",
            "escalationFallbackMsg: string;",
        ],
        "types/shopConfig.ts",
    )
    validate_required_substrings(
        dashboard_mock_content,
        [
            "todayServedCount: 286",
            "aiReplyRate: 0.912",
            "escalationCount: 5",
            "avgFirstResponseMs: 2300",
            "unrepliedCount: 2",
            "yesterdayServedCount: 255",
        ],
        "mock/dashboard.ts",
    )
    validate_required_substrings(
        shop_mock_content,
        [
            "url: '/api/shops'",
            "method: 'get'",
            "method: 'patch'",
            "method: 'post'",
            "platform: 'pdd'",
            "platform: 'douyin'",
            "platform: 'qianniu'",
            "cookieValid: false",
        ],
        "mock/shop.ts",
    )
    validate_required_substrings(
        shop_config_mock_content,
        [
            "url: '/api/shops/:id/config'",
            "method: 'get'",
            "method: 'put'",
            "humanAgentName",
            "escalationRules",
            "llmMode: 'custom'",
            "llmMode: 'global'",
        ],
        "mock/shopConfig.ts",
    )
    validate_required_substrings(
        mock_index_content,
        ["import './shop';", "import './shopConfig';"],
        "mock/index.ts",
    )
    validate_required_substrings(
        dashboard_view_content,
        [
            "<el-skeleton :loading=\"loading\" animated>",
            "onMounted(async () => {",
            "summary.value = await fetchDashboardSummary();",
            "未回复会话",
            "消息趋势图 - 待接入",
            "metric-card--alert",
        ],
        "views/Dashboard.vue",
    )
    validate_required_substrings(
        shop_manage_view_content,
        [
            "<el-tabs v-model=\"activePlatform\"",
            "platformOrder: Platform[] = ['pdd', 'douyin', 'qianniu']",
            "<ShopCard",
            "<ShopEditDialog",
            "fetchShopList",
            "toggleShopAi",
            "toggleShopStatus",
            "handleEdit",
            "handleConfigSaved",
            "openAddDialog",
            "v-model=\"dialogVisible\"",
            ":shop-id=\"selectedShopId\"",
            "添加店铺",
            "<el-badge :value=\"shopCountByPlatform[platform]\" />",
        ],
        "views/ShopManage.vue",
    )
    validate_forbidden_substrings(
        shop_manage_view_content,
        ["这里将在下一步接入分平台 Tab、店铺卡片和启停操作。", "新建店铺表单 - 待接入"],
        "views/ShopManage.vue",
    )
    validate_required_substrings(
        shop_card_content,
        [
            "defineProps<{",
            "shop: Shop;",
            "defineEmits<{",
            "toggleAi: [shopId: string, enabled: boolean];",
            "toggleStatus: [shopId: string];",
            "emit('edit', shop.id)",
            "@change=\"handleAiToggle\"",
        ],
        "components/ShopCard.vue",
    )
    validate_required_substrings(
        shop_edit_dialog_content,
        [
            "<el-dialog v-model=\"dialogVisible\" title=\"编辑店铺\" width=\"680px\"",
            "<el-collapse v-model=\"activePanels\"",
            "基础信息",
            "AI 配置",
            "转人工规则",
            "fetchShopConfig",
            "saveShopConfig",
            "添加规则",
            "customApiKey",
            "humanAgentName",
            "escalationFallbackMsg",
        ],
        "components/ShopEditDialog.vue",
    )
    validate_required_substrings(
        app_layout_content,
        [
            "import Sidebar from '@/components/layout/Sidebar.vue';",
            "padding-top: 24px;",
        ],
        "components/layout/AppLayout.vue",
    )
    validate_forbidden_substrings(
        app_layout_content,
        ["<Topbar", "Topbar.vue", "import Topbar"],
        "components/layout/AppLayout.vue",
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
    validate_required_substrings(
        sidebar_content,
        ["多平台智能客服", "RPA 自动化客服系统"],
        "Sidebar.vue",
    )
    validate_forbidden_substrings(
        sidebar_content,
        ["Customer Service OS", "前端控制台骨架"],
        "Sidebar.vue",
    )


def test_validation_helpers_raise_for_missing_contract() -> None:
    with pytest.raises(ValueError):
        validate_route_paths(["/dashboard"])

    with pytest.raises(ValueError):
        validate_required_substrings("axios.create()", ["import.meta.env.VITE_API_BASE_URL"], "request.ts")

    with pytest.raises(ValueError):
        validate_forbidden_substrings("Bell", ["Bell"], "router/index.ts")
