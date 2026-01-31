import base64
import os
from typing import Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from pydantic import AnyHttpUrl, BaseModel, Field

from browser import (
    BrowserUnavailableError,
    BrowserManager,
    PlaywrightError,
    PlaywrightTimeoutError,
)

API_TOKEN = os.getenv("API_TOKEN")

app = FastAPI(title="Playwright Browser Service")

browser_manager = BrowserManager.from_env()


async def verify_token(request: Request):
    if not API_TOKEN:
        return
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"type": "auth_error", "message": "Missing or invalid Authorization header"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(
            status_code=403,
            detail={"type": "auth_error", "message": "Invalid API token"},
        )


def _error_detail(code: str, message: str) -> dict:
    return {"type": code, "message": message}


@app.on_event("startup")
async def on_startup():
    await browser_manager.start()


@app.on_event("shutdown")
async def on_shutdown():
    await browser_manager.stop()


@app.get("/health")
async def health():
    status = "available" if browser_manager.is_ready() else "unavailable"
    return {"status": "ok", "browser": status}


class ScreenshotRequest(BaseModel):
    url: AnyHttpUrl
    width: int = Field(default=1280, ge=200, le=3840)
    height: int = Field(default=800, ge=200, le=2160)
    full_page: bool = False


@app.post("/screenshot", dependencies=[Depends(verify_token)])
async def screenshot(req: ScreenshotRequest):
    if not browser_manager.is_ready():
        raise HTTPException(503, detail=_error_detail("browser_unavailable", "Browser is not ready"))

    if not browser_manager.is_url_allowed(str(req.url)):
        raise HTTPException(403, detail=_error_detail("url_not_allowed", "URL host is not allowed"))

    try:
        async with browser_manager.page_context(width=req.width, height=req.height) as page:
            await page.goto(str(req.url), wait_until="load", timeout=browser_manager.timeout_ms)
            png_bytes = await page.screenshot(full_page=req.full_page, type="png")
            b64 = base64.b64encode(png_bytes).decode()
            return {"screenshot": b64}
    except PlaywrightTimeoutError:
        raise HTTPException(504, detail=_error_detail("timeout", "Navigation timed out"))
    except PlaywrightError as exc:
        raise HTTPException(502, detail=_error_detail("playwright_error", str(exc)))


class NavigateRequest(BaseModel):
    url: AnyHttpUrl
    wait_until: Optional[Literal["load", "domcontentloaded", "networkidle"]] = "load"


@app.post("/navigate", dependencies=[Depends(verify_token)])
async def navigate(req: NavigateRequest):
    if not browser_manager.is_ready():
        raise HTTPException(503, detail=_error_detail("browser_unavailable", "Browser is not ready"))

    if not browser_manager.is_url_allowed(str(req.url)):
        raise HTTPException(403, detail=_error_detail("url_not_allowed", "URL host is not allowed"))

    try:
        async with browser_manager.page_context(width=1280, height=800) as page:
            await page.goto(str(req.url), wait_until=req.wait_until or "load", timeout=browser_manager.timeout_ms)
            title = await page.title()
            final_url = page.url
            html = await page.content()
            return {"title": title, "url": final_url, "html": html}
    except PlaywrightTimeoutError:
        raise HTTPException(504, detail=_error_detail("timeout", "Navigation timed out"))
    except PlaywrightError as exc:
        raise HTTPException(502, detail=_error_detail("playwright_error", str(exc)))


class ExecuteRequest(BaseModel):
    url: AnyHttpUrl
    script: str = Field(min_length=1, max_length=10000)


@app.post("/execute", dependencies=[Depends(verify_token)])
async def execute(req: ExecuteRequest):
    if not browser_manager.is_ready():
        raise HTTPException(503, detail=_error_detail("browser_unavailable", "Browser is not ready"))

    if not browser_manager.is_url_allowed(str(req.url)):
        raise HTTPException(403, detail=_error_detail("url_not_allowed", "URL host is not allowed"))

    try:
        async with browser_manager.page_context(width=1280, height=800) as page:
            # Navigate with domcontentloaded for faster execute start
            await page.goto(str(req.url), wait_until="domcontentloaded", timeout=browser_manager.timeout_ms)
            result = await page.evaluate(req
codex
I put together a full Playwright + FastAPI service with persistent browser lifecycle, per-request contexts, token auth, timeouts, optional resource blocking, and Zeabur-ready Docker/launch config. Drop these files into `/app` as requested.

`main.py`