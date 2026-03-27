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


@app.post("/scan")
async def html_scan() -> RedirectResponse:
    await service.run_scan(trigger="manual")
    return RedirectResponse(url="/", status_code=303)


@app.post("/replenish")
async def html_replenish(count: int = Form(0)) -> RedirectResponse:
    await service.run_manual_replenish(count=count or None)
    return RedirectResponse(url="/", status_code=303)
