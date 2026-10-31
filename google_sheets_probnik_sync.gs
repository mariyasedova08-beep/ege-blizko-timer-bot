const EGE_BOT_SYNC_URL = 'https://ege-blizko-timer-bot-production.up.railway.app/sheets/probnik-sync';
const EGE_BOT_SYNC_SECRET = 'PASTE_SECRET_HERE';

function syncProbnikResultsToBot() {
  if (EGE_BOT_SYNC_SECRET === 'PASTE_SECRET_HERE' || !/^https:\/\//.test(EGE_BOT_SYNC_URL)) {
    throw new Error('Синхронизация выключена: сначала проверь адрес сервера и секрет.');
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = ss.getSheets();
  const payload = {
    spreadsheet_title: ss.getName(),
    spreadsheet_id: ss.getId(),
    synced_at: new Date().toISOString(),
    sheets: []
  };

  sheets.forEach(sheet => {
    const sheetName = String(sheet.getName() || '').trim();
    if (!sheetName || sheetName.toUpperCase() === 'СТАТИСТИКА') return;

    const values = sheet.getDataRange().getDisplayValues();
    if (!values || values.length < 2) return;

    const headers = values[0].map(v => String(v || '').trim());
    const eventCol = findHeader(headers, ['МЕРОПРИЯТИЕ']);
    const dateCol = findHeader(headers, ['ДАТА']);
    const primaryCol = findHeader(headers, ['ПЕРВИЧНЫЙ БАЛЛ']);
    const secondaryCol = findHeader(headers, ['ВТОРИЧНЫЙ БАЛЛ']);
    const statusCol = findHeader(headers, ['СТАТУС']);
    if (eventCol < 0 || dateCol < 0) return;

    const taskCols = {};
    for (let task = 1; task <= 34; task++) {
      const idx = headers.findIndex(h => h === String(task));
      if (idx >= 0) taskCols[String(task)] = idx;
    }

    const results = [];
    for (let r = 1; r < values.length; r++) {
      const row = values[r];
      const eventName = String(row[eventCol] || '').trim();
      const eventDate = String(row[dateCol] || '').trim();
      if (!eventName || !eventDate) continue;
      const publicationStatus = statusCol >= 0 ? String(row[statusCol] || '').trim().toLowerCase() : '';
      // Status-aware EGE sheets publish only explicitly approved rows.
      // ЕГЭ must fail closed: missing status is NOT permission to publish.
      // Legacy OГЭ spreadsheets without status retain historical behavior.
      const isEge = /ЕГЭ/i.test(ss.getName());
      if (isEge && (statusCol < 0 || publicationStatus !== 'опубликовано')) continue;
      if (!isEge && statusCol >= 0 && publicationStatus !== 'опубликовано') continue;

      const tasks = {};
      Object.keys(taskCols).forEach(task => {
        const value = String(row[taskCols[task]] || '').trim();
        if (value !== '') tasks[task] = value;
      });

      const primaryScore = primaryCol >= 0 ? String(row[primaryCol] || '').trim() : '';
      const secondaryScore = secondaryCol >= 0 ? String(row[secondaryCol] || '').trim() : '';
      const hasResult = primaryScore !== '' || secondaryScore !== '' || Object.keys(tasks).length > 0;
      if (!hasResult) continue;

      results.push({
        event_name: eventName,
        event_date: eventDate,
        primary_score: primaryScore,
        secondary_score: secondaryScore,
        publication_status: statusCol >= 0 ? 'опубликовано' : 'legacy',
        tasks: tasks
      });
    }

    payload.sheets.push({
      sheet_name: sheetName,
      student_name: sheetName,
      results: results
    });
  });

  const response = UrlFetchApp.fetch(
    EGE_BOT_SYNC_URL + '?secret=' + encodeURIComponent(EGE_BOT_SYNC_SECRET),
    {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    }
  );

  const code = response.getResponseCode();
  const body = response.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error('Ошибка синхронизации: HTTP ' + code + ' ' + body);
  }

  const result = JSON.parse(body);
  SpreadsheetApp.getActive().toast(
    'Синхронизировано: ' + result.rows_saved + ' результатов, ' + result.students + ' учеников',
    'ЕГЭ БЛИЗКО',
    8
  );
}

// Safe inspection: reads this spreadsheet only; no request and no Telegram messages.
function previewProbnikPublication() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const isEge = /ЕГЭ/i.test(ss.getName());
  let ready = 0, drafts = 0, withoutStatus = 0, missingScore = 0;
  ss.getSheets().forEach(sheet => {
    if (String(sheet.getName()).trim().toUpperCase() === 'СТАТИСТИКА') return;
    const rows = sheet.getDataRange().getDisplayValues();
    if (rows.length < 2) return;
    const headers = rows[0].map(v => String(v || '').trim());
    const statusCol = findHeader(headers, ['СТАТУС']);
    const primaryCol = findHeader(headers, ['ПЕРВИЧНЫЙ БАЛЛ']);
    const secondaryCol = findHeader(headers, ['ВТОРИЧНЫЙ БАЛЛ']);
    if (isEge && statusCol < 0) { withoutStatus++; return; }
    for (let i = 1; i < rows.length; i++) {
      const status = statusCol >= 0 ? String(rows[i][statusCol] || '').trim().toLowerCase() : 'legacy';
      if (status !== 'опубликовано') { drafts++; continue; }
      if ((primaryCol < 0 || !String(rows[i][primaryCol] || '').trim()) &&
          (secondaryCol < 0 || !String(rows[i][secondaryCol] || '').trim())) {
        missingScore++; continue;
      }
      ready++;
    }
  });
  SpreadsheetApp.getUi().alert(
    'ЕГЭ БЛИЗКО — предпросмотр (без отправки)',
    'Готовы к публикации: ' + ready +
    '\\nЧерновики/не проверено: ' + drafts +
    '\\nЛистов без статуса: ' + withoutStatus +
    '\\nОпубликовано без баллов: ' + missingScore +
    '\\n\\nНичего не отправлено.',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ЕГЭ БЛИЗКО')
    .addItem('Проверить публикацию (без отправки)', 'previewProbnikPublication')
    .addItem('Синхронизировать результаты', 'syncProbnikResultsToBot')
    .addToUi();
}

function findHeader(headers, variants) {
  const normalized = headers.map(h => String(h || '').trim().toUpperCase());
  for (let i = 0; i < variants.length; i++) {
    const idx = normalized.indexOf(String(variants[i]).trim().toUpperCase());
    if (idx >= 0) return idx;
  }
  return -1;
}
