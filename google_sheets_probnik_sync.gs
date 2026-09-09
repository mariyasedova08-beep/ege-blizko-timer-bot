const EGE_BOT_SYNC_URL = 'https://ege-blizko-timer-bot-production.up.railway.app/sheets/probnik-sync';
const EGE_BOT_SYNC_SECRET = 'PASTE_SECRET_HERE';

function syncProbnikResultsToBot() {
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

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ЕГЭ БЛИЗКО')
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
