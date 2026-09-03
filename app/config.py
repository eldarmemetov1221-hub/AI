"""Загрузка глобальных настроек и конфигураций компаний-клиентов (тенантов).

Каждая компания (агентство недвижимости) — это отдельный "тенант": своя папка
в TENANTS_DIR со своим config.json, базой объектов properties.json и API-ключом.
Так один сервер обслуживает много компаний в разных городах: у каждой свой
город, валюта, язык и база — агент подстраивается автоматически.

ИИ работает через OpenRouter (OpenAI-совместимый API). Тот же код подходит и
для OpenAI/ChatGPT — достаточно поменять LLM_BASE_URL и LLM_API_KEY.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Настройки ИИ (OpenRouter по умолчанию; можно указать OpenAI) ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
MODEL_ID = os.getenv("MODEL_ID", "deepseek/deepseek-chat-v3-0324:free")
# Необязательные заголовки для рейтинга приложения в OpenRouter
APP_URL = os.getenv("APP_URL", "")
APP_NAME = os.getenv("APP_NAME", "Real Estate AI Agent")

# --- Настройки сервера ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
# Глобальная ссылка для заявок (Google Apps Script /exec или n8n). Применяется,
# если у тенанта в config.json поле lead_webhook_url не задано.
LEAD_WEBHOOK_URL = os.getenv("LEAD_WEBHOOK_URL", "").strip()
TENANTS_DIR = Path(os.getenv("TENANTS_DIR", "tenants"))
DATA_DIR = Path("data")


@dataclass
class Tenant:
    """Конфигурация одной компании-клиента."""

    tenant_id: str
    name: str
    api_key: str
    city: str = ""          # город/рынок работы компании
    currency: str = "USD"   # валюта цен в базе
    language: str = "auto"
    tone: str = ""
    contacts: dict = field(default_factory=dict)
    google_sheet_id: str = ""
    lead_webhook_url: str = ""  # сюда можно подключить n8n
    properties: list[dict] = field(default_factory=list)

    @property
    def property_count(self) -> int:
        return len(self.properties)


def _load_tenant(folder: Path) -> Tenant | None:
    config_path = folder / "config.json"
    if not config_path.exists():
        return None
    config = json.loads(config_path.read_text(encoding="utf-8"))

    properties: list[dict] = []
    props_path = folder / "properties.json"
    if props_path.exists():
        properties = json.loads(props_path.read_text(encoding="utf-8"))

    return Tenant(
        tenant_id=folder.name,
        name=config.get("name", folder.name),
        api_key=config.get("api_key", ""),
        city=config.get("city", ""),
        currency=config.get("currency", "USD"),
        language=config.get("language", "auto"),
        tone=config.get("tone", ""),
        contacts=config.get("contacts", {}),
        google_sheet_id=config.get("google_sheet_id", ""),
        lead_webhook_url=config.get("lead_webhook_url", ""),
        properties=properties,
    )


@lru_cache(maxsize=1)
def load_tenants() -> dict[str, Tenant]:
    """Загружает всех тенантов из TENANTS_DIR (кэшируется)."""
    tenants: dict[str, Tenant] = {}
    if not TENANTS_DIR.exists():
        return tenants
    for folder in sorted(TENANTS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        tenant = _load_tenant(folder)
        if tenant:
            tenants[tenant.tenant_id] = tenant
    return tenants


def get_tenant(tenant_id: str) -> Tenant | None:
    return load_tenants().get(tenant_id)


def reload_tenants() -> None:
    """Сбросить кэш — например после обновления базы объектов."""
    load_tenants.cache_clear()
