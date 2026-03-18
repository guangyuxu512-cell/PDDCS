from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"


def validate_required_substrings(content: str, required_substrings: list[str], label: str) -> None:
    missing = [item for item in required_substrings if item not in content]
    if missing:
        raise ValueError(f"{label} 缺少关键内容: {', '.join(missing)}")


def validate_forbidden_substrings(content: str, forbidden_substrings: list[str], label: str) -> None:
    existing = [item for item in forbidden_substrings if item in content]
    if existing:
        raise ValueError(f"{label} 不应包含: {', '.join(existing)}")


def test_shop_dialog_enhancement_files_exist() -> None:
    expected_files = {
        "src/components/ShopEditDialog.vue",
        "src/components/ShopCard.vue",
        "src/views/ShopManage.vue",
        "src/views/Settings.vue",
        "src/types/shopConfig.ts",
        "src/api/knowledge.ts",
        "src/api/settings.ts",
        "src/api/shop.ts",
        "src/mock/knowledge.ts",
        "src/mock/settings.ts",
        "src/mock/shop.ts",
        "src/mock/shopConfig.ts",
    }

    existing = {
        str(path.relative_to(FRONTEND_DIR)).replace("\\", "/")
        for path in FRONTEND_DIR.rglob("*")
        if path.is_file()
    }
    assert expected_files.issubset(existing)


def test_shop_dialog_enhancement_contracts() -> None:
    shop_config_type = (FRONTEND_DIR / "src" / "types" / "shopConfig.ts").read_text(encoding="utf-8")
    knowledge_api = (FRONTEND_DIR / "src" / "api" / "knowledge.ts").read_text(encoding="utf-8")
    settings_api = (FRONTEND_DIR / "src" / "api" / "settings.ts").read_text(encoding="utf-8")
    shop_api = (FRONTEND_DIR / "src" / "api" / "shop.ts").read_text(encoding="utf-8")
    knowledge_mock = (FRONTEND_DIR / "src" / "mock" / "knowledge.ts").read_text(encoding="utf-8")
    settings_mock = (FRONTEND_DIR / "src" / "mock" / "settings.ts").read_text(encoding="utf-8")
    shop_mock = (FRONTEND_DIR / "src" / "mock" / "shop.ts").read_text(encoding="utf-8")
    shop_config_mock = (FRONTEND_DIR / "src" / "mock" / "shopConfig.ts").read_text(encoding="utf-8")
    shop_card = (FRONTEND_DIR / "src" / "components" / "ShopCard.vue").read_text(encoding="utf-8")
    shop_edit_dialog = (FRONTEND_DIR / "src" / "components" / "ShopEditDialog.vue").read_text(
        encoding="utf-8"
    )
    shop_manage = (FRONTEND_DIR / "src" / "views" / "ShopManage.vue").read_text(encoding="utf-8")
    settings_view = (FRONTEND_DIR / "src" / "views" / "Settings.vue").read_text(encoding="utf-8")

    validate_required_substrings(
        shop_config_type,
        [
            "username: string;",
            "password: string;",
            "knowledgePaths: string[];",
            "useGlobalKnowledge: boolean;",
        ],
        "types/shopConfig.ts",
    )
    validate_required_substrings(
        knowledge_api,
        [
            "fetchKnowledgeFileList",
            "request.get<ApiResponse<string[]>>('/knowledge/files')",
        ],
        "api/knowledge.ts",
    )
    validate_required_substrings(
        settings_api,
        [
            "testLlmConnection",
            "request.post<ApiResponse<{ ok: boolean; message: string }>>('/settings/test-llm', params)",
        ],
        "api/settings.ts",
    )
    validate_required_substrings(
        shop_api,
        [
            "openShopBrowser",
            "request.post<ApiResponse<null>>(`/shops/${shopId}/open-browser`)",
        ],
        "api/shop.ts",
    )
    validate_required_substrings(
        knowledge_mock,
        [
            "url: '/api/knowledge/files'",
            "filter((path) => path.endsWith('.md'))",
        ],
        "mock/knowledge.ts",
    )
    validate_required_substrings(
        settings_mock,
        [
            "url: '/api/settings/test-llm'",
            "setTimeout(resolve, 1000)",
            "LLM 连接测试成功，模型响应正常",
        ],
        "mock/settings.ts",
    )
    validate_required_substrings(
        shop_mock,
        [
            "url: '/api/shops/:id/open-browser'",
            "data: null",
        ],
        "mock/shop.ts",
    )
    validate_required_substrings(
        shop_config_mock,
        [
            "username:",
            "password:",
            "knowledgePaths:",
            "useGlobalKnowledge:",
        ],
        "mock/shopConfig.ts",
    )
    validate_required_substrings(
        shop_card,
        [
            "Monitor",
            "open-browser",
            "打开客服后台",
            "emit('open-browser', shop.id)",
        ],
        "components/ShopCard.vue",
    )
    validate_required_substrings(
        shop_manage,
        [
            "@open-browser=\"handleOpenBrowser\"",
            "openShopBrowser",
            "正在打开客服后台，请在浏览器窗口中操作",
        ],
        "views/ShopManage.vue",
    )
    validate_required_substrings(
        shop_edit_dialog,
        [
            "店铺账号",
            "店铺密码",
            "知识库绑定",
            "fetchKnowledgeFileList",
            "同时使用全局知识库",
            "knowledgePaths",
            "useGlobalKnowledge",
            "测试连接",
            "handleTestCustomConnection",
            "testLlmConnection",
        ],
        "components/ShopEditDialog.vue",
    )
    validate_required_substrings(
        settings_view,
        [
            "测试连接",
            "handleTestConnection",
            "testingConnection",
            "testLlmConnection",
            "连接失败:",
            "LLM 连接测试成功，模型响应正常",
        ],
        "views/Settings.vue",
    )


def test_shop_dialog_enhancement_validation_helpers_raise() -> None:
    with pytest.raises(ValueError):
        validate_required_substrings("partial", ["missing"], "sample")

    with pytest.raises(ValueError):
        validate_forbidden_substrings("contains bad", ["bad"], "sample")
