from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend" / "src"


def test_shop_manage_polling_and_cleanup_are_present() -> None:
    shop_manage = (FRONTEND_DIR / "views" / "ShopManage.vue").read_text(encoding="utf-8")

    required = [
        "onUnmounted",
        "const SHOP_STATUS_POLL_INTERVAL_MS = 5000;",
        "pollTimer = setInterval(async () => {",
        "shops.value = await fetchShopList();",
        "clearInterval(pollTimer);",
    ]

    missing = [item for item in required if item not in shop_manage]
    assert not missing, f"ShopManage.vue 缺少轮询关键逻辑: {missing}"


def test_shop_config_switch_fields_are_wired_through_dialog_and_mock() -> None:
    shop_config_type = (FRONTEND_DIR / "types" / "shopConfig.ts").read_text(encoding="utf-8")
    shop_edit_dialog = (FRONTEND_DIR / "components" / "ShopEditDialog.vue").read_text(encoding="utf-8")
    shop_config_mock = (FRONTEND_DIR / "mock" / "shopConfig.ts").read_text(encoding="utf-8")

    required_type_fields = [
        "autoRestart: boolean;",
        "forceOnline: boolean;",
    ]
    required_dialog_fields = [
        "v-model=\"formState.autoRestart\"",
        "v-model=\"formState.forceOnline\"",
        "autoRestart: false,",
        "forceOnline: false,",
        "autoRestart: config.autoRestart ?? false,",
        "forceOnline: config.forceOnline ?? false,",
        "autoRestart: config.autoRestart,",
        "forceOnline: config.forceOnline,",
    ]
    required_mock_fields = [
        "autoRestart:",
        "forceOnline:",
    ]

    missing_type = [item for item in required_type_fields if item not in shop_config_type]
    missing_dialog = [item for item in required_dialog_fields if item not in shop_edit_dialog]
    missing_mock = [item for item in required_mock_fields if item not in shop_config_mock]

    assert not missing_type, f"shopConfig.ts 缺少字段: {missing_type}"
    assert not missing_dialog, f"ShopEditDialog.vue 缺少字段透传: {missing_dialog}"
    assert not missing_mock, f"mock/shopConfig.ts 缺少默认字段: {missing_mock}"
