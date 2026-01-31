import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional, Set
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright,
    Browser,
    Playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_csv(name: str) -> Set[str]:
    val = os.getenv(name, "")
    return {v.strip().lower() for v in val.split(",") if v.strip()}


class BrowserUnavailableError(RuntimeError):
    pass


class BrowserManager:
    DEFAULT_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        block_resource_types: Optional[Set[str]] = None,
        allowed_hosts: Optional[Set[str]] = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.block_resource_types = block_resource_types or set()
        self.allowed_hosts = allowed_hosts or set()
        self._playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._start_lock = asyncio.Lock()

    @classmethod
    def from_env(cls):
        headless = _env_bool("BROWSER_HEADLESS", True)
        timeout_ms = int(os.getenv("REQUEST_TIMEOUT_MS", "30000"))
        block_resources = _env_bool("BLOCK_RESOURCES", False)
        block_types = _parse_csv("BLOCK_RESOURCE_TYPES")
        if block_resources and not block_types:
            # Default block resource types if block_resources is true but no types specified
            block_types = {"image", "media", "font"}
        allowed_hosts = _parse_csv("ALLOWED_HOSTS")
        return cls(
            headless=headless,
            timeout_ms=timeout_ms,
            block_resource_types=block_types if block_resources or block_types else set(),
            allowed_hosts=allowed_hosts,
        )

    async def start(self):
        async with self._start_lock:
            if self.browser is not None:
                return
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless, args=self.DEFAULT_LAUNCH_ARGS
            )

    async def stop(self):
        async with self._start_lock:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    def is_ready(self) -> bool:
        return self.browser is not None

    def is_url_allowed(self, url: str) -> bool:
        if not self.allowed_hosts:
            return True  # Allow all if no whitelist

        hostname = urlparse(url).hostname
        if not hostname:
            return False
        hostname = hostname.lower()
        for entry in self.allowed_hosts:
            entry = entry.lower()
            if entry.startswith("*."):
                # wildcard subdomain match
                if hostname == entry[2:] or hostname.endswith("." + entry[2:]):
                    return True
            elif hostname == entry:
                return True
        return False

    @asynccontextmanager
    async def page_context(
        self,
        *,
        width: int,
        height: int,
    ):
        if not self.browser:
            raise BrowserUnavailableError("Browser is not started")
        context = await self.browser.new_context(viewport={"width": width, "height": height})
        # Setup resource blocking if configured
        if self.block_resource_types:

            async def route_handler(route):
                if route.request.resource_type.lower() in self.block_resource_types:
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", route_handler)

        page = await context.new_page()
        page.set_default_timeout(self.timeout_ms)
        try:
            yield page
        finally:
            await context.close()