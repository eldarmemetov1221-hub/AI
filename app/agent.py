"""ИИ-агент-риелтор поверх Claude API.

Ведёт диалог с клиентом, объясняет и советует, подбирает объекты под бюджет
(инструмент search_properties), а когда клиент готов на просмотр — собирает
контакты и сохраняет лид (инструмент save_lead).

История диалога хранится в памяти по session_id. Для одного сервера этого
достаточно; для нескольких воркеров подключите общее хранилище (Redis и т.п.)
в MEMORY ниже.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from . import config, leads, properties
from .config import Tenant

client = anthropic.Anthropic()

# session_id -> список сообщений в формате Claude API
MEMORY: dict[str, list[dict[str, Any]]] = {}

MAX_TOOL_ITERATIONS = 6  # защита от зацикливания


TOOLS = [
    {
        "name": "search_properties",
        "description": (
            "Подобрать объекты недвижимости из базы компании по критериям клиента. "
            "Используй, как только понял бюджет и хотя бы примерные пожелания. "
            "Возвращает список подходящих объектов. Никогда не придумывай объекты — "
            "показывай клиенту только то, что вернул этот инструмент."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_type": {
                    "type": "string",
                    "enum": ["sale", "rent"],
                    "description": "Тип сделки: продажа (sale) или аренда (rent).",
                },
                "property_type": {
                    "type": "string",
                    "description": "Тип объекта, напр. apartment, house, studio, commercial.",
                },
                "district": {"type": "string", "description": "Район или город."},
                "min_price": {"type": "number", "description": "Минимальная цена."},
                "max_price": {"type": "number", "description": "Максимальная цена (бюджет клиента)."},
                "min_rooms": {"type": "integer", "description": "Минимум комнат."},
                "max_rooms": {"type": "integer", "description": "Максимум комнат."},
                "min_area": {"type": "number", "description": "Минимальная площадь, м²."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "save_lead",
        "description": (
            "Сохранить контактные данные клиента в конце разговора, когда он "
            "согласен на просмотр или просит перезвонить. Вызывай ТОЛЬКО когда есть "
            "как минимум имя и телефон. Перед вызовом убедись, что клиент сам их назвал."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя клиента."},
                "phone": {"type": "string", "description": "Телефон клиента."},
                "viewing_datetime": {
                    "type": "string",
                    "description": "Когда клиенту удобно смотреть объект (как он сказал).",
                },
                "property_id": {"type": "string", "description": "ID объекта из базы, который смотрит клиент."},
                "property_title": {"type": "string", "description": "Название/адрес объекта."},
                "budget": {"type": "string", "description": "Бюджет клиента."},
                "notes": {"type": "string", "description": "Кратко: пожелания клиента."},
            },
            "required": ["name", "phone"],
            "additionalProperties": False,
        },
    },
]


def build_system_prompt(tenant: Tenant) -> str:
    contacts = ""
    if tenant.contacts:
        contacts = "\nКонтакты компании (если клиент попросит): " + json.dumps(
            tenant.contacts, ensure_ascii=False
        )
    lang = (
        "Отвечай на языке клиента (определяй автоматически по его сообщениям)."
        if tenant.language == "auto"
        else f"Отвечай на языке: {tenant.language}."
    )
    tone = tenant.tone or (
        "Дружелюбный, профессиональный, без навязчивости. Говори как живой опытный риелтор."
    )
    return f"""Ты — ИИ-риелтор компании «{tenant.name}». Ты работаешь 24/7 и общаешься с клиентами вместо менеджера.

Твои задачи:
1. Тепло поприветствовать и выяснить потребность: покупка или аренда, тип жилья, район, бюджет, число комнат, для кого.
2. Объяснять и советовать честно — что подойдёт, что нет и почему, помогать выбрать в рамках бюджета.
3. Подбирать объекты ТОЛЬКО через инструмент search_properties. Не выдумывай цены, адреса и наличие. Если ничего не нашлось — честно скажи и предложи изменить критерии.
4. Показывать 2–4 лучших варианта коротко и понятно: цена, район, комнаты, площадь, ключевые плюсы.
5. Когда клиент заинтересован — предложить записать на просмотр. Собери имя, телефон и удобные дату/время, уточни какой объект. Затем ВЫЗОВИ save_lead. После успешного сохранения подтверди клиенту, что менеджер свяжется.

Правила:
- {lang}
- Тон: {tone}
- Отвечай кратко и по делу, не перегружай текстом. Задавай по одному-двум вопросам за раз.
- Никогда не проси и не сохраняй лишние персональные данные — только имя, телефон и пожелания по просмотру.
- Не обещай того, чего нет в базе, и не называй точную юридическую/налоговую информацию — по таким вопросам направляй к менеджеру.{contacts}
"""


def _run_tool(tenant: Tenant, session_id: str, name: str, tool_input: dict) -> Any:
    if name == "search_properties":
        found = properties.search_properties(tenant.properties, **tool_input)
        if not found:
            return {"count": 0, "properties": [], "message": "Нет объектов под эти критерии."}
        return {"count": len(found), "properties": found}

    if name == "save_lead":
        result = leads.save_lead(tenant, session_id=session_id, **tool_input)
        return {"saved": True, "delivery": result["delivery"]}

    return {"error": f"Неизвестный инструмент: {name}"}


def chat(tenant: Tenant, session_id: str, user_message: str) -> dict[str, Any]:
    """Обрабатывает одно сообщение клиента и возвращает ответ агента.

    Возвращает: {"reply": str, "lead_saved": bool}
    """
    history = MEMORY.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    system = build_system_prompt(tenant)
    lead_saved = False

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=config.MODEL_ID,
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "save_lead":
                lead_saved = True
            output = _run_tool(tenant, session_id, block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )
        history.append({"role": "user", "content": tool_results})

    reply = " ".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    if not reply:
        reply = "Извините, повторите, пожалуйста — я не расслышал."

    return {"reply": reply, "lead_saved": lead_saved}


def reset_session(session_id: str) -> None:
    MEMORY.pop(session_id, None)
