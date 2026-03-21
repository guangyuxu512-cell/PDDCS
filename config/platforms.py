"""Platform YAML configuration loader."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PLATFORM_CONFIG_PATH = Path(__file__).resolve().with_name("platforms.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Platform config must be a mapping: {path}")
    return dict(raw)


@lru_cache(maxsize=1)
def load_platforms_config() -> dict[str, Any]:
    """Load the full platform YAML configuration."""
    if not PLATFORM_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Platform config not found: {PLATFORM_CONFIG_PATH}")
    return _read_yaml(PLATFORM_CONFIG_PATH)


def reset_platform_config_cache() -> None:
    """Clear the in-memory YAML cache."""
    load_platforms_config.cache_clear()


def get_platform_config(platform: str) -> dict[str, Any]:
    """Return configuration for one platform."""
    config = load_platforms_config().get(platform)
    if not isinstance(config, dict):
        raise KeyError(f"Platform config missing or invalid: {platform}")
    return dict(config)


def get_platform_selector_values(platform: str) -> dict[str, tuple[str, ...]]:
    """Return selector values normalized to tuples."""
    selectors = get_platform_config(platform).get("selectors")
    if not isinstance(selectors, dict):
        raise KeyError(f"Platform selectors missing or invalid: {platform}")

    normalized: dict[str, tuple[str, ...]] = {}
    for key, value in selectors.items():
        if isinstance(value, str):
            values = (value,)
        elif isinstance(value, list) and all(isinstance(item, str) and item for item in value):
            values = tuple(value)
        else:
            raise ValueError(f"Selector '{platform}.{key}' must be a string or non-empty string list")
        if not values:
            raise ValueError(f"Selector '{platform}.{key}' is empty")
        normalized[str(key)] = values
    return normalized
