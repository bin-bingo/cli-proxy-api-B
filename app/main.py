from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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


@app.post("/api/test/cpa")
async def api_test_cpa() -> JSONResponse:
    return JSONResponse(service.test_cpa_connection())


@app.post("/api/test/registration")
async def api_test_registration() -> JSONResponse:
    return JSONResponse(service.test_registration_connection())


@app.post("/scan")
async def html_scan() -> RedirectResponse:
    await service.run_scan(trigger="manual")
    return RedirectResponse(url="/", status_code=303)


@app.post("/replenish")
async def html_replenish(count: int = Form(0)) -> RedirectResponse:
    await service.run_manual_replenish(count=count or None)
    return RedirectResponse(url="/", status_code=303)


@app.post("/settings/account-keys")
async def html_save_account_keys(request: Request) -> Response:
    form = await request.form()
    updates: dict[str, object] = {}
    for field in (
        "cliproxy_base_url",
        "cliproxy_management_key",
        "registration_key",
        "registration_base_url",
    ):
        if field in form:
            updates[field] = str(form.get(field, ""))

    await service.update_runtime_settings(updates)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": "saved"})
    return RedirectResponse(url="/", status_code=303)


@app.post("/settings/strategy")
async def html_save_strategy_settings(
    request: Request,
    min_healthy_count: int | None = Form(None),
    target_healthy_count: int | None = Form(None),
    auto_scan_enabled: str | None = Form(None),
    auto_replenish_enabled: str | None = Form(None),
    replenish_mode: str | None = Form(None),
    replenish_concurrency: int | None = Form(None),
    replenish_email_type: str | None = Form(None),
    replenish_auto_cpa: str | None = Form(None),
) -> Response:
    updates: dict[str, object] = {}
    if min_healthy_count is not None:
        updates["min_healthy_count"] = min_healthy_count
    if target_healthy_count is not None:
        updates["target_healthy_count"] = target_healthy_count
    updates["auto_scan_enabled"] = auto_scan_enabled is not None
    updates["auto_replenish_enabled"] = auto_replenish_enabled is not None
    if replenish_mode is not None:
        updates["replenish_mode"] = replenish_mode
    if replenish_concurrency is not None:
        updates["replenish_concurrency"] = replenish_concurrency
    if replenish_email_type is not None:
        updates["replenish_email_type"] = replenish_email_type
    updates["replenish_auto_cpa"] = replenish_auto_cpa is not None

    await service.update_runtime_settings(updates)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": "saved"})
    return RedirectResponse(url="/", status_code=303)


@app.post("/settings/advanced")
async def html_save_advanced_settings(
    request: Request,
    cliproxy_timeout_seconds: int | None = Form(None),
    auth_dir: str | None = Form(None),
    usage_exhaust_threshold: float | None = Form(None),
    auto_cleanup_enabled: str | None = Form(None),
    cleanup_invalid_enabled: str | None = Form(None),
    cleanup_quota_enabled: str | None = Form(None),
    cleanup_rate_limit_enabled: str | None = Form(None),
    replenish_command: str | None = Form(None),
) -> Response:
    updates: dict[str, object] = {}
    if cliproxy_timeout_seconds is not None:
        updates["cliproxy_timeout_seconds"] = cliproxy_timeout_seconds
    if auth_dir is not None:
        updates["auth_dir"] = auth_dir
    if usage_exhaust_threshold is not None:
        updates["usage_exhaust_threshold"] = usage_exhaust_threshold
    updates["auto_cleanup_enabled"] = auto_cleanup_enabled is not None
    updates["cleanup_invalid_enabled"] = cleanup_invalid_enabled is not None
    updates["cleanup_quota_enabled"] = cleanup_quota_enabled is not None
    updates["cleanup_rate_limit_enabled"] = cleanup_rate_limit_enabled is not None
    if replenish_command is not None:
        updates["replenish_command"] = replenish_command

    await service.update_runtime_settings(updates)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": "saved"})
    return RedirectResponse(url="/", status_code=303)


@app.post("/test/cpa")
async def html_test_cpa() -> RedirectResponse:
    service.test_cpa_connection()
    return RedirectResponse(url="/", status_code=303)


@app.post("/test/registration")
async def html_test_registration() -> RedirectResponse:
    service.test_registration_connection()
    return RedirectResponse(url="/", status_code=303)
