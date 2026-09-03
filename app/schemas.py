"""Pydantic-схемы запросов/ответов API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="Сообщение клиента.")
    session_id: str = Field(..., description="Идентификатор диалога (генерирует виджет).")


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    lead_saved: bool = False
