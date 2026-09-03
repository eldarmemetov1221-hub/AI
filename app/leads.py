"""Сохранение лида (данных клиента) в конце разговора.

Лид уходит в несколько приёмников — работает то, что настроено у компании:
  1. Google Sheets  — если у тенанта задан google_sheet_id и настроен сервис-аккаунт;
  2. Вебхук (n8n)   — если задан lead_webhook_url (сюда удобно подключить любую
                      автоматизацию: уведомление менеджеру, запись в CRM и т.д.);
  3. Локальный файл data/leads.jsonl — всегда, как резервная копия.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from . import config
from .config import Tenant

_SHEET_HEADER = [
    "timestamp",
    "name",
    "phone",
    "viewing_datetime",
    "property_id",
    "property_title",
    "budget",
    "notes",
    "session_id",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_local(lead: dict[str, Any]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = config.DATA_DIR / "leads.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(lead, ensure_ascii=False) + "\n")


def _save_webhook(url: str, lead: dict[str, Any]) -> bool:
    try:
        # follow_redirects — Google Apps Script и n8n часто отвечают 302-переадресацией.
        resp = httpx.post(url, json=lead, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — приёмник не должен ронять ответ клиенту
        print(f"[leads] webhook failed: {exc}")
        return False


def _save_google_sheet(sheet_id: str, lead: dict[str, Any]) -> bool:
    if not config.GOOGLE_SERVICE_ACCOUNT_FILE:
        return False
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
        gc = gspread.authorize(creds)
        worksheet = gc.open_by_key(sheet_id).sheet1

        # Проставляем заголовок, если лист пустой.
        if not worksheet.get_all_values():
            worksheet.append_row(_SHEET_HEADER, value_input_option="USER_ENTERED")

        row = [str(lead.get(col, "")) for col in _SHEET_HEADER]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[leads] google sheets failed: {exc}")
        return False


def save_lead(
    tenant: Tenant,
    *,
    name: str,
    phone: str,
    viewing_datetime: str = "",
    property_id: str = "",
    property_title: str = "",
    budget: str = "",
    notes: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Сохраняет лид во все настроенные приёмники. Возвращает сам лид и статус доставки."""
    lead = {
        "timestamp": _now_iso(),
        "tenant_id": tenant.tenant_id,
        "name": name,
        "phone": phone,
        "viewing_datetime": viewing_datetime,
        "property_id": property_id,
        "property_title": property_title,
        "budget": budget,
        "notes": notes,
        "session_id": session_id,
    }

    delivery = {"local": False, "webhook": False, "google_sheet": False}

    _save_local(lead)
    delivery["local"] = True

    if tenant.lead_webhook_url:
        delivery["webhook"] = _save_webhook(tenant.lead_webhook_url, lead)

    if tenant.google_sheet_id:
        delivery["google_sheet"] = _save_google_sheet(tenant.google_sheet_id, lead)

    return {"lead": lead, "delivery": delivery}
