/**
 * Приём заявок (лидов) от ИИ-риелтора и запись в текущую Google-таблицу.
 *
 * Как подключить (5 минут, без ключей и сервисных аккаунтов):
 *  1. Создай Google-таблицу (sheets.new).
 *  2. Меню: Расширения → Apps Script.
 *  3. Удали то, что там есть, вставь весь этот файл, нажми Сохранить (значок дискеты).
 *  4. Нажми "Развернуть" (Deploy) → "Новое развёртывание" (New deployment).
 *  5. Тип: выбери "Веб-приложение" (Web app).
 *  6. "Кто имеет доступ" (Who has access): выбери "Все" (Anyone). Нажми "Развернуть".
 *  7. Разреши доступ (Authorize) своей учёткой Google.
 *  8. Скопируй URL веб-приложения (заканчивается на /exec) — это и есть "ссылка".
 *  9. Вставь этот URL в tenants/<компания>/config.json в поле "lead_webhook_url".
 *
 * Теперь, когда клиент договаривается о просмотре, агент сам добавит строку:
 * дата записи, имя, телефон, дата/время просмотра, объект и т.д.
 */

var HEADER = [
  'Записано',            // когда пришла заявка
  'Имя',                 // name
  'Телефон',             // phone
  'Дата/время просмотра',// viewing_datetime
  'Объект',              // property_title
  'ID объекта',          // property_id
  'Бюджет',              // budget
  'Пожелания',           // notes
  'Компания',            // tenant_id
  'Сессия'               // session_id
];

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];

    // Заголовок — только если лист пустой.
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADER);
    }

    sheet.appendRow([
      data.timestamp || new Date().toISOString(),
      data.name || '',
      data.phone || '',
      data.viewing_datetime || '',
      data.property_title || '',
      data.property_id || '',
      data.budget || '',
      data.notes || '',
      data.tenant_id || '',
      data.session_id || ''
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// Позволяет открыть URL в браузере и проверить, что скрипт живой.
function doGet() {
  return ContentService
    .createTextOutput('Real Estate AI lead endpoint is running.')
    .setMimeType(ContentService.MimeType.TEXT);
}
