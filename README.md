# Real Estate AI Agent 🏠🤖

ИИ-агент-риелтор для агентств недвижимости (рынки **Европы и США**). Общается с
клиентами 24/7, объясняет и советует, подбирает объекты под бюджет из базы
компании и в конце разговора записывает контакты клиента (имя, телефон, дата
просмотра, объект) в **Google Sheets** / вебхук (**n8n**) / локальный файл.

ИИ работает через **OpenRouter** (есть бесплатные модели). Тот же код подходит
для **OpenAI/ChatGPT** — меняются только адрес и ключ в `.env`.

Продукт **мультитенантный**: один сервер обслуживает много компаний в разных
городах. У каждой компании свой **город, валюта, язык и база объектов** — агент
подстраивается автоматически. Каждая компания встраивает чат к себе на сайт
**одной строкой** `<script>`. В репозитории два примера: `demo` (Майами, USD) и
`berlin` (Берлин, EUR, немецкий).

---

## Архитектура

```
Сайт компании ──<script widget.js>──▶  FastAPI /chat  ──▶  OpenRouter/OpenAI (агент)
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
cp .env.example .env        # вписать LLM_API_KEY (ключ OpenRouter или OpenAI)
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

## Модель и провайдер

По умолчанию **OpenRouter** с бесплатной моделью
`meta-llama/llama-3.3-70b-instruct:free` (`MODEL_ID` в `.env`). Бесплатные модели
годятся для тестов; для стабильного подбора и записи лидов лучше платная
`openai/gpt-4o-mini` — она надёжнее вызывает инструменты.

Чтобы работать напрямую через **OpenAI/ChatGPT**, в `.env`:

```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
MODEL_ID=gpt-4o-mini
```

## Замечания для продакшена

- **CORS** — в `.env` перечислите домены компаний в `ALLOWED_ORIGINS`.
- **Память диалога** сейчас в ОЗУ (`agent.MEMORY`). Для нескольких воркеров
  подключите Redis.
- Добавьте **rate limiting** и антиспам на `/chat` (публичный виджет).
- Секреты Google/ключи в репозиторий не коммитим (см. `.gitignore`).
