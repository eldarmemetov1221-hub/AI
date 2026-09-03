"""FastAPI-сервер ИИ-агента для агентств недвижимости.

Мультитенантный: один сервер обслуживает много компаний. Компания встраивает
виджет на свой сайт одной строкой <script>, указав свой tenant_id.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import agent, config
from .schemas import ChatRequest, ChatResponse

app = FastAPI(title="Real Estate AI Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
WIDGET_DIR = Path(__file__).resolve().parent.parent / "widget"


def _resolve_tenant(tenant_id: str, api_key: str | None):
    tenant = config.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    # Если у компании задан ключ — проверяем его (для server-to-server интеграций).
    if tenant.api_key and tenant.api_key != (api_key or ""):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


@app.get("/health")
def health():
    tenants = config.load_tenants()
    return {
        "status": "ok",
        "model": config.MODEL_ID,
        "tenants": {tid: t.property_count for tid, t in tenants.items()},
    }


@app.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
):
    tenant = _resolve_tenant(x_tenant_id, x_api_key)
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    result = agent.chat(tenant, body.session_id, body.message.strip())
    return ChatResponse(
        reply=result["reply"],
        session_id=body.session_id,
        lead_saved=result["lead_saved"],
    )


@app.post("/reset")
def reset(
    body: ChatRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
):
    _resolve_tenant(x_tenant_id, x_api_key)
    agent.reset_session(body.session_id)
    return JSONResponse({"status": "reset"})


@app.get("/widget.js")
def widget_js():
    path = WIDGET_DIR / "widget.js"
    return FileResponse(path, media_type="application/javascript")


@app.get("/")
def demo():
    path = STATIC_DIR / "demo.html"
    if path.exists():
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"service": "Real Estate AI Agent", "docs": "/docs"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=True)
