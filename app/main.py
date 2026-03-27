from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ROOT_DIR, settings
from .service import service


app = FastAPI(title=settings.app_name, version="0.1.0")
app.mount(
    "/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static"
)
templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))


@app.on_event("startup")
async def startup() -> None:
    await service.startup()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "status": service.get_status(),
            "settings": service.settings_snapshot(),
        },
    )


@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse(service.get_status())


@app.get("/api/history")
async def api_history(limit: int = 50) -> JSONResponse:
    return JSONResponse({"items": service.get_history(limit=limit)})


@app.post("/api/scan")
async def api_scan() -> JSONResponse:
    state = await service.run_scan(trigger="manual")
    return JSONResponse(state.to_dict())


@app.post("/api/replenish")
async def api_replenish(count: int | None = None) -> JSONResponse:
    result = await service.run_manual_replenish(count=count)
    return JSONResponse(result)


@app.post("/api/settings")
async def api_save_settings(request: Request) -> JSONResponse:
    payload = await request.json()
    runtime = await service.update_runtime_settings(
        payload if isinstance(payload, dict) else {}
    )
    return JSONResponse({"settings": runtime.to_dict()})


@app.post("/scan")
async def html_scan() -> RedirectResponse:
    await service.run_scan(trigger="manual")
    return RedirectResponse(url="/", status_code=303)


@app.post("/replenish")
async def html_replenish(count: int = Form(0)) -> RedirectResponse:
    await service.run_manual_replenish(count=count or None)
    return RedirectResponse(url="/", status_code=303)


@app.post("/settings")
async def html_save_settings(
    cliproxy_base_url: str = Form(""),
    cliproxy_management_key: str = Form(""),
    cliproxy_timeout_seconds: int = Form(20),
    auth_dir: str = Form(""),
    min_healthy_count: int = Form(20),
    target_healthy_count: int = Form(30),
    usage_exhaust_threshold: float = Form(95.0),
    auto_scan_enabled: str | None = Form(None),
    auto_replenish_enabled: str | None = Form(None),
    replenish_command: str = Form(""),
    registration_key: str = Form(""),
    registration_base_url: str = Form(""),
    registration_cpa_token: str = Form(""),
) -> RedirectResponse:
    await service.update_runtime_settings(
        {
            "cliproxy_base_url": cliproxy_base_url,
            "cliproxy_management_key": cliproxy_management_key,
            "cliproxy_timeout_seconds": cliproxy_timeout_seconds,
            "auth_dir": auth_dir,
            "min_healthy_count": min_healthy_count,
            "target_healthy_count": target_healthy_count,
            "usage_exhaust_threshold": usage_exhaust_threshold,
            "auto_scan_enabled": auto_scan_enabled is not None,
            "auto_replenish_enabled": auto_replenish_enabled is not None,
            "replenish_command": replenish_command,
            "registration_key": registration_key,
            "registration_base_url": registration_base_url,
            "registration_cpa_token": registration_cpa_token,
        }
    )
    return RedirectResponse(url="/", status_code=303)
