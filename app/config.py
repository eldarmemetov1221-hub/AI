"""Загрузка глобальных настроек и конфигураций компаний-клиентов (тенантов).

Каждая компания (агентство недвижимости) — это отдельный "тенант": своя папка
в TENANTS_DIR со своим config.json, базой объектов properties.json и API-ключом.
Так один сервер обслуживает много компаний, а мы продаём им доступ к агенту.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Глобальные настройки сервера ---
MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-5")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
TENANTS_DIR = Path(os.getenv("TENANTS_DIR", "tenants"))
DATA_DIR = Path("data")


@dataclass
class Tenant:
    """Конфигурация одной компании-клиента."""

    tenant_id: str
    name: str
    api_key: str
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
