import os
import base64
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import AnyHttpUrl, BaseModel, Field
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from browser import browser_manager, BrowserUnavailableError

app = FastAPI(title="Playwright Browser Service")

API_TOKEN = os.getenv("API_TOKEN")


def _error_detail(kind: str, message: str) -> dict:
    return {"type": kind, "message": message}


async def verify_token(request: Request) -> None:
    if not API_TOKEN:
        return
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail=_error_detail("unauthorized", "Missing Bearer token"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail=_error_detail("forbidden", "Invalid token"))


def _require_browser() -> None:
    if not browser_manager.is_ready():
        raise HTTPException(
            status_code=503,
            detail=_error_detail("browser_unavailable", "Browser is not ready"),
        )


def _ensure_url_allowed(url: str) -> None:
    if not browser_manager.is_url_allowed(url):
        raise HTTPException(
            status_code=403,
            detail=_error_detail("forbidden", "URL is not allowed"),
        )


class ScreenshotRequest(BaseModel):
    url: AnyHttpUrl
    width: int = Field(default=1280, ge=200, le=4096)
    height: int = Field(default=800, ge=200, le=4096)
    full_page: bool = False


class NavigateRequest(BaseModel):
    url: AnyHttpUrl
    wait_until: Optional[Literal["load", "domcontentloaded", "networkidle"]] = None


class ExecuteRequest(BaseModel):
    url: AnyHttpUrl
    script: str = Field(min_length=1, max_length=10000)


@app.on_event("startup")
async def _startup() -> None:
    await browser_manager.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await browser_manager.stop()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "browser": "available" if browser_manager.is_ready() else "unavailable",
    }


@app.post("/screenshot", dependencies=[Depends(verify_token)])
async def screenshot(payload: ScreenshotRequest) -> dict:
    _require_browser()
    _ensure_url_allowed(str(payload.url))

    try:
        async with browser_manager.page_context(width=payload.width, height=payload.height) as page:
            await page.goto(
                str(payload.url),
                wait_until="load",
                timeout=browser_manager.timeout_ms,
            )
            png_bytes = await page.screenshot(full_page=payload.full_page, type="png")
    except PlaywrightTimeoutError:
        raise HTTPException(status_code=504, detail=_error_detail("timeout", "Navigation timed out"))
    except PlaywrightError as exc:
        raise HTTPException(status_code=502, detail=_error_detail("playwright_error", str(exc)))
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_error_detail("browser_unavailable", str(exc)))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("internal_error", str(exc)))

    return {"image_base64": base64.b64encode(png_bytes).decode("ascii")}


@app.post("/navigate", dependencies=[Depends(verify_token)])
async def navigate(payload: NavigateRequest) -> dict:
    _require_browser()
    _ensure_url_allowed(str(payload.url))

    wait_until = payload.wait_until or "load"

    try:
        async with browser_manager.page_context() as page:
            await page.goto(
                str(payload.url),
                wait_until=wait_until,
                timeout=browser_manager.timeout_ms,
            )
            title = await page.title()
            final_url = page.url
            html = await page.content()
    except PlaywrightTimeoutError:
        raise HTTPException(status_code=504, detail=_error_detail("timeout", "Navigation timed out"))
    except PlaywrightError as exc:
        raise HTTPException(status_code=502, detail=_error_detail("playwright_error", str(exc)))
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_error_detail("browser_unavailable", str(exc)))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("internal_error", str(exc)))

    return {"title": title, "url": final_url, "html": html}


@app.post("/execute", dependencies=[Depends(verify_token)])
async def execute(payload: ExecuteRequest) -> dict:
    _require_browser()
    _ensure_url_allowed(str(payload.url))

    try:
        async with browser_manager.page_context() as page:
            await page.goto(
                str(payload.url),
                wait_until="domcontentloaded",
                timeout=browser_manager.timeout_ms,
            )
            result = await page.evaluate(payload.script)
    except PlaywrightTimeoutError:
        raise HTTPException(status_code=504, detail=_error_detail("timeout", "Navigation timed out"))
    except PlaywrightError as exc:
        raise HTTPException(status_code=502, detail=_error_detail("playwright_error", str(exc)))
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_error_detail("browser_unavailable", str(exc)))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("internal_error", str(exc)))

    return {"result": result}
