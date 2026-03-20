"""Selector configuration helpers for adapter fallbacks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SelectorConfig:
    """Represents a primary selector with ordered fallbacks."""

    primary: str
    fallbacks: list[str] | None = None

    def all(self) -> list[str]:
        selectors = [self.primary]
        if self.fallbacks:
            selectors.extend(self.fallbacks)
        return selectors
