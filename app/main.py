"""FastAPI-сервер ИИ-агента для агентств недвижимости.

Мультитенантный: один сервер обслуживает много компаний. Компания встраивает
виджет на свой сайт одной строкой <script>, указав свой tenant_id.
"""
from __future__ import annotations

from pathlib import Path

import html

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

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


@app.get("/", response_class=HTMLResponse)
def demo(tenant: str = "demo"):
    """Персональная демо-страница агентства.

    Ссылка вида /?tenant=имя показывает виджет с базой и названием этой компании —
    удобно отправлять конкретному агентству как «вот ваш агент».
    """
    t = config.get_tenant(tenant) or config.get_tenant("demo")
    if t is None:
        return HTMLResponse("<h1>Real Estate AI Agent</h1><p>No tenants configured.</p>")
    name = html.escape(t.name)
    tid = html.escape(t.tenant_id)
    city = html.escape(t.city or "")
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{name} — AI Assistant</title>
<style>
 body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#111;background:#f3f4f6}}
 .hero{{max-width:760px;margin:0 auto;padding:80px 24px}}
 h1{{font-size:34px;margin:0 0 12px}}
 p{{font-size:17px;line-height:1.6;color:#374151}}
 .card{{background:#fff;border-radius:16px;padding:24px;margin-top:24px;box-shadow:0 4px 16px rgba(0,0,0,.06)}}
 .tag{{display:inline-block;background:#e0edff;color:#1d4ed8;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:600}}
</style></head>
<body>
 <div class="hero">
   <span class="tag">AI Assistant demo</span>
   <h1>{name}</h1>
   <p>{('Serving ' + city + '. ') if city else ''}Click the chat button in the bottom-right corner and ask about a
   property — it answers 24/7, matches homes to your budget, and books viewings automatically.</p>
   <div class="card">
     <strong>Add it to your site with one line:</strong>
     <pre style="overflow:auto"><code>&lt;script src="/widget.js" data-tenant="{tid}"&gt;&lt;/script&gt;</code></pre>
   </div>
 </div>
 <script src="/widget.js" data-tenant="{tid}" data-title="{name}"></script>
</body></html>""")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=True)
