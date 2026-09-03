"""ИИ-агент-риелтор поверх OpenRouter (OpenAI-совместимый API).

Работает с ЛЮБОЙ чат-моделью (включая бесплатные модели OpenRouter), потому что
не полагается на «инструменты»/function-calling — многие бесплатные модели их не
поддерживают. Вместо этого:

  * вся база объектов компании вшивается прямо в системный промпт, и агент
    рекомендует только из неё;
  * лид (контакты клиента) агент отдаёт в конце спец-меткой [[LEAD]]{...}[[/LEAD]],
    которую мы вырезаем из ответа и сохраняем (Google Sheets / вебхук / файл).

Провайдер и модель задаются в config (LLM_BASE_URL, LLM_API_KEY, MODEL_ID).
Тот же код работает с OpenAI/ChatGPT — меняются только адрес и ключ.

Рынки Европы и США: у каждой компании свой город и валюта — агент подстраивается
через системный промпт и базу объектов тенанта.

История диалога хранится в памяти по session_id.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from . import config, leads
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

# Сколько объектов максимум вшивать в промпт (для больших баз — ограничение).
MAX_LISTINGS_IN_PROMPT = 60

_LEAD_RE = re.compile(r"\[\[LEAD\]\](.*?)\[\[/LEAD\]\]", re.DOTALL)


def _strip_markdown(text: str) -> str:
    """Убирает markdown-разметку, чтобы в чате не было символов *, #, ` и _."""
    # **жирный** / *курсив* -> обычный текст
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"`{1,3}(.+?)`{1,3}", r"\1", text)
    # заголовки "### " и маркеры списка "* " / "- " в начале строк
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^(\s*)[*•]\s+", r"\1- ", text)
    # одиночные оставшиеся * и обрамляющие _слово_
    text = text.replace("*", "")
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    return text.strip()


def build_system_prompt(tenant: Tenant) -> str:
    contacts = ""
    if tenant.contacts:
        contacts = "\nCompany contacts (share if the client asks): " + json.dumps(
            tenant.contacts, ensure_ascii=False
        )
    lang = (
        "Always reply in the SAME language the client writes in — detect it from "
        "their most recent message and match it exactly. If the client writes in "
        "English, reply in English. Never switch to another language on your own."
        if tenant.language == "auto"
        else f"Always reply in this language: {tenant.language}."
    )
    tone = tenant.tone or (
        "Friendly, professional, never pushy. Talk like a real experienced local realtor."
    )
    market = f"You operate in {tenant.city}. " if tenant.city else ""
    currency = f"Prices are in {tenant.currency}. " if tenant.currency else ""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")

    listings = tenant.properties[:MAX_LISTINGS_IN_PROMPT]
    listings_json = json.dumps(listings, ensure_ascii=False, indent=2)

    return f"""You are an AI real estate agent for "{tenant.name}". You work 24/7 and talk to clients instead of a human agent. {market}{currency}

Your job:
1. Greet warmly and find out the need: buy or rent, property type, area, budget, number of rooms, who it's for.
2. Explain and advise honestly — what fits, what doesn't, and why; help them choose within budget.
3. Recommend ONLY from the LISTINGS below. Never invent prices, addresses or availability. If nothing matches, say so honestly and suggest adjusting the criteria.
4. Show the 2–4 best options briefly and clearly: price, area, rooms, size, key highlights.
5. When the client is interested, offer to book a viewing. Collect their name, phone, and a SPECIFIC date and time for the viewing. Ask it plainly, e.g. "What exact date and time works for you? For example, 2026-09-06 at 15:00." If the client says something relative like "this Saturday at noon", convert it to a real calendar date using today's date below. Also note which property.

Today's date is {today}. Use it to turn relative dates ("today", "tomorrow", "this Saturday") into an actual calendar date.

LISTINGS (the company's current database — the only properties you may offer):
{listings_json}

Rules:
- {lang}
- Tone: {tone}
- Write plain text only. Do NOT use Markdown or any formatting symbols such as *, **, #, backticks or underscores. For lists use a simple dash "-" or numbers. Emojis are fine.
- Keep replies short and to the point. Ask one or two questions at a time.
- Never ask for or store extra personal data — only name, phone and viewing preferences.
- Don't promise anything not in the listings, and don't give exact legal/tax advice — refer those to a human manager.{contacts}

CAPTURING THE LEAD (very important):
When — and only when — the client has given you BOTH their name and phone number, end your reply with a single hidden line in EXACTLY this format (the client will not see it):
[[LEAD]]{{"name":"...","phone":"...","viewing_datetime":"...","property_id":"...","property_title":"...","budget":"...","notes":"..."}}[[/LEAD]]
Fill what you know, leave unknown fields as empty strings. For "viewing_datetime" always write a concrete absolute date and time in the format YYYY-MM-DD HH:MM (24-hour), e.g. "2026-09-06 15:00" — never a vague phrase like "this Saturday". Put it on its own line at the very end, after your normal message to the client. Do not mention this line or show JSON to the client. Do not output it until you actually have both name and phone.
"""


def _extract_and_save_lead(tenant: Tenant, session_id: str, text: str) -> tuple[str, bool]:
    """Ищет метку [[LEAD]]...[[/LEAD]] в ответе, сохраняет лид и убирает метку
    из текста, который увидит клиент. Возвращает (очищенный_текст, сохранён?)."""
    match = _LEAD_RE.search(text)
    if not match:
        return text.strip(), False

    saved = False
    try:
        data = json.loads(match.group(1).strip())
        name = str(data.get("name", "")).strip()
        phone = str(data.get("phone", "")).strip()
        if name and phone:
            leads.save_lead(
                tenant,
                session_id=session_id,
                name=name,
                phone=phone,
                viewing_datetime=str(data.get("viewing_datetime", "")),
                property_id=str(data.get("property_id", "")),
                property_title=str(data.get("property_title", "")),
                budget=str(data.get("budget", "")),
                notes=str(data.get("notes", "")),
            )
            saved = True
    except (json.JSONDecodeError, TypeError):
        pass

    cleaned = _LEAD_RE.sub("", text).strip()
    return cleaned, saved


def chat(tenant: Tenant, session_id: str, user_message: str) -> dict[str, Any]:
    """Обрабатывает одно сообщение клиента и возвращает ответ агента.

    Возвращает: {"reply": str, "lead_saved": bool}
    """
    history = MEMORY.get(session_id)
    if history is None:
        history = [{"role": "system", "content": build_system_prompt(tenant)}]
        MEMORY[session_id] = history

    history.append({"role": "user", "content": user_message})

    completion = client.chat.completions.create(
        model=config.MODEL_ID,
        messages=history,
        max_tokens=1024,
    )
    raw = completion.choices[0].message.content or ""
    history.append({"role": "assistant", "content": raw})

    reply, lead_saved = _extract_and_save_lead(tenant, session_id, raw)
    reply = _strip_markdown(reply)
    if not reply:
        reply = "Sorry, could you say that again?"

    return {"reply": reply, "lead_saved": lead_saved}


def reset_session(session_id: str) -> None:
    MEMORY.pop(session_id, None)
