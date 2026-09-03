"""Подбор объектов недвижимости из базы конкретной компании.

Это "инструмент" (tool), которым пользуется ИИ-агент: он передаёт критерии
клиента (бюджет, комнаты, район, тип), а функция возвращает подходящие объекты.
Работает по локальному JSON — на этом же интерфейсе позже легко заменить
источник на реальную БД или CRM компании, не трогая агента.
"""
from __future__ import annotations

from typing import Any


def _matches(prop: dict[str, Any], **criteria) -> bool:
    deal = criteria.get("deal_type")
    if deal and str(prop.get("deal_type", "")).lower() != str(deal).lower():
        return False

    ptype = criteria.get("property_type")
    if ptype and str(prop.get("type", "")).lower() != str(ptype).lower():
        return False

    district = criteria.get("district")
    if district and district.lower() not in str(prop.get("district", "")).lower():
        return False

    price = prop.get("price")
    min_price = criteria.get("min_price")
    max_price = criteria.get("max_price")
    if isinstance(price, (int, float)):
        if min_price is not None and price < min_price:
            return False
        if max_price is not None and price > max_price:
            return False

    rooms = prop.get("rooms")
    min_rooms = criteria.get("min_rooms")
    max_rooms = criteria.get("max_rooms")
    if isinstance(rooms, (int, float)):
        if min_rooms is not None and rooms < min_rooms:
            return False
        if max_rooms is not None and rooms > max_rooms:
            return False

    min_area = criteria.get("min_area")
    area = prop.get("area")
    if min_area is not None and isinstance(area, (int, float)) and area < min_area:
        return False

    return True


def search_properties(
    properties: list[dict[str, Any]],
    *,
    deal_type: str | None = None,
    property_type: str | None = None,
    district: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_rooms: int | None = None,
    max_rooms: int | None = None,
    min_area: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Фильтрует базу объектов по критериям и возвращает до `limit` штук,
    отсортированных по цене (по возрастанию)."""
    results = [
        p
        for p in properties
        if _matches(
            p,
            deal_type=deal_type,
            property_type=property_type,
            district=district,
            min_price=min_price,
            max_price=max_price,
            min_rooms=min_rooms,
            max_rooms=max_rooms,
            min_area=min_area,
        )
    ]
    results.sort(key=lambda p: p.get("price") if isinstance(p.get("price"), (int, float)) else float("inf"))
    return results[:limit]


def get_property(properties: list[dict[str, Any]], property_id: str) -> dict[str, Any] | None:
    for p in properties:
        if str(p.get("id")) == str(property_id):
            return p
    return None
