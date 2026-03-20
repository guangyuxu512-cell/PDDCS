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


def test_frontend_shop_crud_scan_contracts() -> None:
    shop_api = (FRONTEND_DIR / "src" / "api" / "shop.ts").read_text(encoding="utf-8")
    shop_card = (FRONTEND_DIR / "src" / "components" / "ShopCard.vue").read_text(encoding="utf-8")
    shop_manage = (FRONTEND_DIR / "src" / "views" / "ShopManage.vue").read_text(encoding="utf-8")

    validate_required_substrings(
        shop_api,
        [
            "export interface CreateShopBody",
            "platform: 'pdd';",
            "createShop",
            "deleteShop",
            "scanDesktopWindows",
            "request.post<ApiResponse<Shop>>('/shops', body)",
            "request.delete<ApiResponse<null>>(`/shops/${shopId}`)",
            "request.post<ApiResponse<Shop[]>>('/shops/scan')",
        ],
        "api/shop.ts",
    )
    validate_required_substrings(
        shop_card,
        [
            "el-popconfirm",
            "确认删除该店铺吗？",
            "delete: [shopId: string];",
            "emit('delete', shop.id)",
            "return '暂无';",
        ],
        "components/ShopCard.vue",
    )
    validate_required_substrings(
        shop_manage,
        [
            "@delete=\"handleDeleteShop\"",
            "createShop",
            "deleteShop",
            "scanDesktopWindows",
            "createDialogVisible",
            "添加拼多多店铺",
            "店铺名称",
            "登录账号",
            "登录密码",
            "show-password",
            "handleCreateShop",
            "handleDeleteShop",
            "handleScanDesktopWindows",
            "扫描桌面窗口",
            "千牛/抖店店铺通过扫描本地桌面窗口自动发现",
            "扫描完成，当前未发现可接管的桌面店铺窗口",
            "店铺创建成功",
            "店铺已删除",
            "v-if=\"platform === 'pdd'\"",
        ],
        "views/ShopManage.vue",
    )
    validate_forbidden_substrings(
        shop_manage,
        ["添加店铺功能待接入"],
        "views/ShopManage.vue",
    )


def test_frontend_shop_crud_scan_validation_helpers_raise() -> None:
    with pytest.raises(ValueError):
        validate_required_substrings("partial", ["missing"], "sample")

    with pytest.raises(ValueError):
        validate_forbidden_substrings("contains bad", ["bad"], "sample")
