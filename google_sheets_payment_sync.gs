const EGE_PAYMENT_SYNC_URL = 'https://ege-blizko-timer-bot-production.up.railway.app/sheets/payment-sync';
const EGE_PAYMENT_SYNC_SECRET = 'PASTE_SAME_SECRET_AS_PROBNIKI';

const EGE_PAYMENT_PERIODS = {
  'СЕНТЯБРЬ': '2026-09',
  'ОКТЯБРЬ': '2026-10',
  'НОЯБРЬ': '2026-11',
  'ДЕКАБРЬ': '2026-12',
  'ЯНВАРЬ': '2027-01',
  'ФЕВРАЛЬ': '2027-02',
  'МАРТ': '2027-03',
  'АПРЕЛЬ': '2027-04',
  'МАЙ': '2027-05'
};

function syncPaymentsToEgeBlizko() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = findPaymentSheet_(ss);
  if (!sheet) {
    throw new Error('Не найдена вкладка «11 КЛАСС»');
  }

  const values = sheet.getDataRange().getDisplayValues();
  if (!values || values.length < 2) {
    throw new Error('Вкладка «11 КЛАСС» пуста');
  }

  const headers = values[0].map(v => String(v || '').trim());
  if (String(headers[0] || '').toUpperCase() !== 'МЕСЯЦ') {
    throw new Error('В A1 должен быть заголовок «МЕСЯЦ»');
  }

  const totalCol = headers.findIndex(h => String(h || '').trim().toUpperCase() === 'ИТОГ');
  if (totalCol < 0) {
    throw new Error('Не найден столбец «ИТОГ»');
  }

  const rowsByPeriod = {};
  for (let r = 1; r < values.length; r++) {
    const monthName = String(values[r][0] || '').trim().toUpperCase();
    const period = EGE_PAYMENT_PERIODS[monthName];
    if (period) rowsByPeriod[period] = values[r];
  }

  const missingMonths = Object.keys(EGE_PAYMENT_PERIODS)
    .filter(monthName => !rowsByPeriod[EGE_PAYMENT_PERIODS[monthName]]);
  if (missingMonths.length) {
    throw new Error('Не найдены месяцы: ' + missingMonths.join(', '));
  }

  const students = [];
  const seen = {};

  for (let col = 1; col < totalCol; col++) {
    const displayName = String(headers[col] || '').trim();
    if (!displayName) continue;

    const nameKey = displayName.toLowerCase().replace(/\s+/g, ' ').trim();
    if (seen[nameKey]) {
      throw new Error('Имя «' + displayName + '» встречается дважды');
    }
    seen[nameKey] = true;

    const coverage = {};
    Object.keys(EGE_PAYMENT_PERIODS).forEach(monthName => {
      const period = EGE_PAYMENT_PERIODS[monthName];
      const row = rowsByPeriod[period];
      const amount = parsePaymentAmount_(row[col]);
      if (amount !== null) coverage[period] = amount;
    });

    const periods = Object.keys(coverage).sort();
    if (!periods.length) continue;

    const monthlyAmount =
      coverage['2026-09'] !== undefined
        ? coverage['2026-09']
        : coverage[periods[0]];

    students.push({
      display_name: displayName,
      monthly_amount: monthlyAmount,
      coverage: coverage
    });
  }

  if (!students.length) {
    throw new Error('Не найдено ни одной оплаты');
  }

  const payload = {
    spreadsheet_title: ss.getName(),
    spreadsheet_id: ss.getId(),
    sheet_name: sheet.getName(),
    synced_at: new Date().toISOString(),
    students: students
  };

  const response = UrlFetchApp.fetch(
    EGE_PAYMENT_SYNC_URL + '?secret=' + encodeURIComponent(EGE_PAYMENT_SYNC_SECRET),
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
  const currentText = result.current_period
    ? ' · текущий месяц: ' + result.current_paid
    : '';

  ss.toast(
    'Оплаты синхронизированы: ' +
      result.students +
      ' учеников, ' +
      result.coverage_count +
      ' отметок' +
      currentText,
    'ЕГЭ БЛИЗКО',
    8
  );
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ЕГЭ БЛИЗКО')
    .addItem('Синхронизировать оплаты', 'syncPaymentsToEgeBlizko')
    .addToUi();
}

function findPaymentSheet_(ss) {
  const target = '11 КЛАСС';
  const sheets = ss.getSheets();
  for (let i = 0; i < sheets.length; i++) {
    if (String(sheets[i].getName() || '').trim().toUpperCase() === target) {
      return sheets[i];
    }
  }
  return null;
}

function parsePaymentAmount_(value) {
  if (value === null || value === undefined || value === '') return null;

  const cleaned = String(value)
    .replace(/₽/g, '')
    .replace(/\u00A0/g, '')
    .replace(/\s/g, '')
    .replace(',', '.')
    .trim();

  if (!cleaned) return null;

  const number = Number(cleaned);
  if (!isFinite(number) || number <= 0) return null;
  return number;
}
