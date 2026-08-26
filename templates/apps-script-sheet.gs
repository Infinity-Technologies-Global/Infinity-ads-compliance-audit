/**
 * Infinity Ads Compliance Audit — Google Sheets receiver.
 *
 * Paste this into the Apps Script project bound to the audit spreadsheet, then
 * deploy it as a Web App. The auditor POSTs one JSON object per run and this
 * script appends it as a row.
 *
 * Setup:
 *   1. Open the spreadsheet, then Extensions > Apps Script.
 *   2. Replace the contents of Code.gs with this file and save.
 *   3. Set SHARED_SECRET below to a value of your choosing, or leave it empty
 *      to accept any request that reaches the URL.
 *   4. Deploy > New deployment > Web app.
 *        Execute as:        Me
 *        Who has access:    Anyone
 *   5. Copy the /exec URL and pass it to the auditor as --sheet-url, or set it
 *      as the ADS_AUDIT_SHEET_URL environment variable.
 *
 * Redeploying after an edit requires Deploy > Manage deployments > Edit >
 * New version. Saving alone does not update the live URL.
 */

/** Tab the rows are appended to. Created automatically when missing. */
var SHEET_NAME = 'Audit Log';

/**
 * Optional shared secret. When set, a request must carry the same value in its
 * `token` field or it is rejected. The Web App URL is unguessable but not
 * private — anyone who obtains it can append rows — so set this when the sheet
 * matters.
 */
var SHARED_SECRET = '';

var HEADERS = [
  'STT',
  'Package',
  'App name',
  'Ngày',
  'Init',
  'Splash',
  'Language',
  'Onboarding',
  'Config',
  'Note',
];

function doPost(request) {
  try {
    var payload = JSON.parse(request.postData.contents);

    if (SHARED_SECRET && payload.token !== SHARED_SECRET) {
      return respond({ ok: false, error: 'unauthorized' });
    }

    var sheet = getSheet();
    var lock = LockService.getScriptLock();

    // Two audits finishing at once would otherwise read the same last row and
    // append the same STT.
    lock.waitLock(30000);
    try {
      var stt = Math.max(0, sheet.getLastRow() - 1) + 1;
      sheet.appendRow([
        stt,
        text(payload.package),
        text(payload.app_name),
        text(payload.date),
        text(payload.init),
        text(payload.splash),
        text(payload.language),
        text(payload.onboarding),
        text(payload.config),
        text(payload.note),
      ]);
    } finally {
      lock.releaseLock();
    }

    return respond({ ok: true, row: stt });
  } catch (error) {
    return respond({ ok: false, error: String(error) });
  }
}

/** Returns the log sheet, creating it with a frozen header row when absent. */
function getSheet() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

/**
 * Coerces a field to a string cell.
 *
 * A leading apostrophe stops Sheets from reading a value such as a package
 * name or a date as a formula or a number.
 */
function text(value) {
  if (value === null || value === undefined) {
    return '';
  }
  var string = String(value);
  return /^[=+\-@]/.test(string) ? "'" + string : string;
}

function respond(body) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}
