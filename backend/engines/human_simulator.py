"""Human-like interaction helpers for Playwright pages."""

from __future__ import annotations

import asyncio
import logging
import random

from playwright.async_api import ElementHandle, Locator, Page


logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
InteractionTarget = str | Locator | ElementHandle


async def _wait(awaitable: Any, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


class HumanSimulator:
    """Wraps common actions with small randomized human-like behavior."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._mouse_position: tuple[float, float] = (0.0, 0.0)

    def _resolve_target(self, selector: InteractionTarget) -> Locator | ElementHandle:
        if isinstance(selector, str):
            return self._page.locator(selector).first
        return selector

    async def random_delay(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        if min_s < 0 or max_s < 0 or min_s > max_s:
            raise ValueError("invalid random delay range")
        delay = random.uniform(min_s, max_s)
        await _wait(asyncio.sleep(delay), timeout_seconds=max(delay + 0.5, 1.0))

    async def simulate_typing(self, selector: InteractionTarget, text: str) -> None:
        target = self._resolve_target(selector)
        await _wait(target.click(timeout=5000), timeout_seconds=6.0)

        try:
            await _wait(target.fill(""), timeout_seconds=6.0)
        except Exception:
            try:
                await _wait(target.press("Control+A"), timeout_seconds=2.0)
                await _wait(target.press("Backspace"), timeout_seconds=2.0)
            except Exception:
                logger.debug("Failed to clear input before typing")

        for char in text:
            if char.strip() and random.random() < 0.08:
                typo_char = random.choice("asdfghjkl")
                await _wait(target.type(typo_char, delay=random.randint(40, 90)), timeout_seconds=2.0)
                await _wait(target.press("Backspace"), timeout_seconds=2.0)
            await _wait(target.type(char, delay=random.randint(50, 140)), timeout_seconds=2.0)
            if random.random() < 0.15:
                await self.random_delay(0.03, 0.12)

    async def bezier_click(self, selector: InteractionTarget) -> None:
        target = self._resolve_target(selector)
        await _wait(target.scroll_into_view_if_needed(timeout=5000), timeout_seconds=6.0)
        box = await _wait(target.bounding_box(), timeout_seconds=6.0)
        if box is None:
            raise RuntimeError("target is not visible for bezier_click")

        start_x, start_y = self._mouse_position
        end_x = box["x"] + (box["width"] * random.uniform(0.35, 0.65))
        end_y = box["y"] + (box["height"] * random.uniform(0.35, 0.65))
        control1_x = start_x + ((end_x - start_x) * random.uniform(0.2, 0.4))
        control1_y = start_y + random.uniform(-80.0, 80.0)
        control2_x = start_x + ((end_x - start_x) * random.uniform(0.6, 0.8))
        control2_y = end_y + random.uniform(-80.0, 80.0)

        for step in range(1, 9):
            t = step / 8
            curve_x = (
                ((1 - t) ** 3 * start_x)
                + (3 * ((1 - t) ** 2) * t * control1_x)
                + (3 * (1 - t) * (t**2) * control2_x)
                + ((t**3) * end_x)
            )
            curve_y = (
                ((1 - t) ** 3 * start_y)
                + (3 * ((1 - t) ** 2) * t * control1_y)
                + (3 * (1 - t) * (t**2) * control2_y)
                + ((t**3) * end_y)
            )
            await _wait(self._page.mouse.move(curve_x, curve_y, steps=1), timeout_seconds=2.0)
            await self.random_delay(0.01, 0.04)

        await _wait(self._page.mouse.down(), timeout_seconds=2.0)
        await self.random_delay(0.02, 0.06)
        await _wait(self._page.mouse.up(), timeout_seconds=2.0)
        self._mouse_position = (end_x, end_y)

    async def random_scroll(self, distance: int = 300) -> None:
        remaining = distance
        step = 120 if distance >= 0 else -120
        while remaining != 0:
            delta = step if abs(remaining) >= abs(step) else remaining
            await _wait(self._page.mouse.wheel(0, delta), timeout_seconds=2.0)
            remaining -= delta
            await self.random_delay(0.03, 0.08)

    async def random_idle(self) -> None:
        action = random.choice(("delay", "scroll", "move"))
        if action == "delay":
            await self.random_delay(0.2, 0.8)
            return
        if action == "scroll":
            await self.random_scroll(random.choice((120, 180, -120)))
            return

        x = random.uniform(80.0, 420.0)
        y = random.uniform(80.0, 260.0)
        await _wait(self._page.mouse.move(x, y, steps=random.randint(4, 10)), timeout_seconds=2.0)
        self._mouse_position = (x, y)
        await self.random_delay(0.05, 0.2)
