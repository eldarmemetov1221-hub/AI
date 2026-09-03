# Real Estate AI Agent 🏠🤖

ИИ-агент-риелтор для агентств недвижимости. Общается с клиентами 24/7,
объясняет и советует, подбирает объекты под бюджет из базы компании и в конце
разговора записывает контакты клиента (имя, телефон, дата просмотра, объект) в
**Google Sheets** / вебхук (**n8n**) / локальный файл.

Продукт **мультитенантный**: один сервер обслуживает много компаний. Каждая
компания встраивает чат к себе на сайт **одной строкой** `<script>`.

---

## Архитектура

```
Сайт компании ──<script widget.js>──▶  FastAPI /chat  ──▶  Claude API (агент)
                                            │                    │
                                            │            search_properties (база компании)
                                            │            save_lead
                                            ▼
                            Google Sheets  /  вебхук n8n  /  data/leads.jsonl
```

**Почему код, а не «чистый» n8n:** для продаваемого мультитенантного продукта
(виджет на любой сайт, своя база у каждого клиента, умный подбор, память
диалога) нужен управляемый бэкенд. n8n при этом отлично подходит как «клей»
для интеграций конкретного клиента — подключается через `lead_webhook_url`.

```
app/
  main.py        FastAPI: /chat, /reset, /health, отдача виджета
  agent.py       Логика агента поверх Claude API + инструменты
  properties.py  Поиск по базе объектов (tool search_properties)
  leads.py       Запись лида: Sheets / вебхук / файл (tool save_lead)
  config.py      Настройки + загрузка тенантов
  schemas.py     Pydantic-схемы
tenants/<id>/    Одна папка = одна компания
  config.json      название, ключ, тон, контакты, sheet_id, webhook
  properties.json  база объектов
widget/widget.js Встраиваемый чат
static/demo.html Демо-страница
```

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # вписать ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Откройте <http://localhost:8000> — демо-страница с виджетом.
Проверка: <http://localhost:8000/health>. API-документация: `/docs`.

## Подключить новую компанию

1. Создайте папку `tenants/<company_id>/`.
2. Положите `config.json` (по образцу `tenants/demo/config.json`) и
   `properties.json` с их объектами.
3. Компания вставляет к себе на сайт:

   ```html
   <script src="https://ВАШ-СЕРВЕР/widget.js"
           data-tenant="company_id"
           data-api="https://ВАШ-СЕРВЕР"
           data-title="Название компании"
           data-color="#2563eb"></script>
   ```

Перезапуск сервера подхватит нового тенанта (или вызовите
`config.reload_tenants()`).

## Формат объекта (`properties.json`)

```json
{
  "id": "A-101",
  "title": "2-комн. квартира, ЖК «Ривер»",
  "deal_type": "sale",          // sale | rent
  "type": "apartment",          // apartment | studio | house | commercial
  "district": "Алматы, Медеуский",
  "price": 42000000,
  "currency": "KZT",
  "rooms": 2,
  "area": 68,
  "highlights": ["ремонт под ключ", "паркинг"]
}
```

## Запись лидов

Лид сохраняется во **все** настроенные приёмники (что настроено, то и работает):

- **Google Sheets** — задайте `google_sheet_id` у тенанта и путь к сервис-аккаунту
  в `GOOGLE_SERVICE_ACCOUNT_FILE`. Выдайте сервис-аккаунту доступ к таблице
  (share на его email). Заголовок создаётся автоматически.
- **Вебхук / n8n** — задайте `lead_webhook_url` у тенанта. Приходит JSON с полями
  лида — дальше n8n делает что угодно (CRM, Telegram менеджеру, письмо).
- **Локальный файл** `data/leads.jsonl` — всегда, как резервная копия.

## Модель

По умолчанию `claude-sonnet-5` (`MODEL_ID` в `.env`) — оптимально по цене для
чат-нагрузки. Для максимального качества поставьте `claude-opus-5`.

## Замечания для продакшена

- **CORS** — в `.env` перечислите домены компаний в `ALLOWED_ORIGINS`.
- **Память диалога** сейчас в ОЗУ (`agent.MEMORY`). Для нескольких воркеров
  подключите Redis.
- Добавьте **rate limiting** и антиспам на `/chat` (публичный виджет).
- Секреты Google/ключи в репозиторий не коммитим (см. `.gitignore`).
