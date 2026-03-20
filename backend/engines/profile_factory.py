"""Profile directory factory for persistent Playwright contexts."""

from __future__ import annotations

import shutil
from pathlib import Path


class ProfileFactory:
    """Creates and manages per-shop Chrome user data directories."""

    def __init__(self, base_dir: str = "data/profiles") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_or_create(self, shop_id: str) -> str:
        shop_dir = self.base_dir / shop_id
        shop_dir.mkdir(parents=True, exist_ok=True)
        return str(shop_dir.absolute())

    def delete(self, shop_id: str) -> bool:
        shop_dir = self.base_dir / shop_id
        if not shop_dir.exists():
            return False
        shutil.rmtree(shop_dir)
        return True

    def list_all(self) -> list[str]:
        return sorted(path.name for path in self.base_dir.iterdir() if path.is_dir())
