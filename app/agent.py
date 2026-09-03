"""ИИ-агент-риелтор поверх OpenRouter (OpenAI-совместимый API).

Работает с бесплатными/платными моделями OpenRouter, а также с OpenAI/ChatGPT —
провайдер задаётся в config (LLM_BASE_URL, LLM_API_KEY, MODEL_ID).

Ведёт диалог, объясняет и советует, подбирает объекты под бюджет
(инструмент search_properties), а когда клиент готов на просмотр — собирает
контакты и сохраняет лид (инструмент save_lead).

Работает на рынки Европы и США: у каждой компании свой город и валюта — агент
подстраивается под них через системный промпт и базу объектов тенанта.

История диалога хранится в памяти по session_id. Для нескольких воркеров
подключите общее хранилище (Redis и т.п.) вместо словаря MEMORY.
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from . import config, leads, properties
from .config import Tenant

_extra_headers = {}
if config.APP_URL:
    _extra_headers["HTTP-Referer"] = config.APP_URL
if config.APP_NAME:
    _extra_headers["X-Title"] = config.APP_NAME

client = OpenAI(
    base_url=config.LLM_BASE_URL,
    api_key=config.LLM_API_KEY or "missing-key",
    default_headers=_extra_headers or None,
)

# session_id -> список сообщений в формате OpenAI chat
MEMORY: dict[str, list[dict[str, Any]]] = {}

MAX_TOOL_ITERATIONS = 6  # защита от зацикливания


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": (
                "Find real estate listings from the company's database by the client's "
                "criteria. Use it as soon as you know the budget and rough preferences. "
                "Returns matching listings. Never invent listings — only show what this "
                "tool returns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deal_type": {
                        "type": "string",
                        "enum": ["sale", "rent"],
                        "description": "Deal type: sale or rent.",
                    },
                    "property_type": {
                        "type": "string",
                        "description": "Property type, e.g. apartment, house, studio, condo, commercial.",
                    },
                    "district": {"type": "string", "description": "Neighborhood, district or city."},
                    "min_price": {"type": "number", "description": "Minimum price."},
                    "max_price": {"type": "number", "description": "Maximum price (client's budget)."},
                    "min_rooms": {"type": "integer", "description": "Minimum number of rooms/bedrooms."},
                    "max_rooms": {"type": "integer", "description": "Maximum number of rooms/bedrooms."},
                    "min_area": {"type": "number", "description": "Minimum area."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": (
                "Save the client's contact details at the end of the conversation, when "
                "they agree to a viewing or ask to be called back. Call ONLY when you have "
                "at least a name and a phone number that the client provided themselves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Client's name."},
                    "phone": {"type": "string", "description": "Client's phone number."},
                    "viewing_datetime": {
                        "type": "string",
                        "description": "When the client wants to view the property (as they said).",
                    },
                    "property_id": {"type": "string", "description": "ID of the listing from the database."},
                    "property_title": {"type": "string", "description": "Listing title/address."},
                    "budget": {"type": "string", "description": "Client's budget."},
                    "notes": {"type": "string", "description": "Short summary of client's preferences."},
                },
                "required": ["name", "phone"],
            },
        },
    },
]


def build_system_prompt(tenant: Tenant) -> str:
    contacts = ""
    if tenant.contacts:
        contacts = "\nCompany contacts (share if the client asks): " + json.dumps(
            tenant.contacts, ensure_ascii=False
        )
    lang = (
        "Reply in the client's own language (auto-detect it from their messages)."
        if tenant.language == "auto"
        else f"Reply in this language: {tenant.language}."
    )
    tone = tenant.tone or (
        "Friendly, professional, never pushy. Talk like a real experienced local realtor."
    )
    market = f"You operate in {tenant.city}. " if tenant.city else ""
    currency = f"Prices are in {tenant.currency}. " if tenant.currency else ""

    return f"""You are an AI real estate agent for "{tenant.name}". You work 24/7 and talk to clients instead of a human agent. {market}{currency}

Your job:
1. Greet warmly and find out the need: buy or rent, property type, area, budget, number of rooms, who it's for.
2. Explain and advise honestly — what fits, what doesn't, and why; help them choose within budget.
3. Find listings ONLY via the search_properties tool. Never invent prices, addresses or availability. If nothing matches, say so honestly and suggest adjusting the criteria.
4. Show the 2–4 best options briefly and clearly: price, area, rooms, size, key highlights.
5. When the client is interested, offer to book a viewing. Collect name, phone and preferred date/time, and note which property. Then CALL save_lead. After it succeeds, confirm that a manager will get in touch.

Rules:
- {lang}
- Tone: {tone}
- Keep replies short and to the point. Ask one or two questions at a time.
- Never ask for or store extra personal data — only name, phone and viewing preferences.
- Don't promise anything not in the database, and don't give exact legal/tax advice — refer those to a human manager.{contacts}
"""


def _run_tool(tenant: Tenant, session_id: str, name: str, args: dict) -> Any:
    if name == "search_properties":
        found = properties.search_properties(tenant.properties, **args)
        if not found:
            return {"count": 0, "properties": [], "message": "No listings match these criteria."}
        return {"count": len(found), "currency": tenant.currency, "properties": found}

    if name == "save_lead":
        result = leads.save_lead(tenant, session_id=session_id, **args)
        return {"saved": True, "delivery": result["delivery"]}

    return {"error": f"Unknown tool: {name}"}


def chat(tenant: Tenant, session_id: str, user_message: str) -> dict[str, Any]:
    """Обрабатывает одно сообщение клиента и возвращает ответ агента.

    Возвращает: {"reply": str, "lead_saved": bool}
    """
    history = MEMORY.get(session_id)
    if history is None:
        # Системный промпт кладём один раз в начало истории диалога.
        history = [{"role": "system", "content": build_system_prompt(tenant)}]
        MEMORY[session_id] = history

    history.append({"role": "user", "content": user_message})
    lead_saved = False
    message = None

    for _ in range(MAX_TOOL_ITERATIONS):
        completion = client.chat.completions.create(
            model=config.MODEL_ID,
            messages=history,
            tools=TOOLS,
            max_tokens=1024,
        )
        message = completion.choices[0].message

        tool_calls = message.tool_calls or []
        # Сохраняем ход ассистента (с возможными вызовами инструментов).
        history.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
                or None,
            }
        )

        if not tool_calls:
            break

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc.function.name == "save_lead":
                lead_saved = True
            output = _run_tool(tenant, session_id, tc.function.name, args)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

    reply = (message.content or "").strip() if message else ""
    if not reply:
        reply = "Sorry, could you say that again?"

    return {"reply": reply, "lead_saved": lead_saved}


def reset_session(session_id: str) -> None:
    MEMORY.pop(session_id, None)
