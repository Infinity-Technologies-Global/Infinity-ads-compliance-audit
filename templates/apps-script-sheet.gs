/**
 * Infinity Ads Compliance Audit — Google Sheets receiver.
 *
 * Paste this into the Apps Script project bound to the audit spreadsheet, then
 * deploy it as a Web App. The auditor POSTs one JSON object per run and this
 * script appends it as a row.
 *
 * This is the script already deployed for Infinity's shared audit sheet. The
 * skill ships the matching URL and secret, so an installed skill logs every run
 * with no setup. Reproduce or rotate the deployment like this:
 *
 * Setup:
 *   1. Open the spreadsheet, then Extensions > Apps Script.
 *   2. Replace the contents of Code.gs with this file and save.
 *   3. Set SHARED_SECRET below to the same value as DEFAULT_SHEET_TOKEN in
 *      scripts/run_audit.py (or, to keep the secret out of the script body, set
 *      a Script Property named ADS_AUDIT_SHEET_TOKEN and leave SHARED_SECRET '').
 *   4. Deploy > New deployment > Web app.
 *        Execute as:        Me
 *        Who has access:    Anyone
 *   5. Put the /exec URL in DEFAULT_SHEET_URL in scripts/run_audit.py.
 *
 * Redeploying after an edit requires Deploy > Manage deployments > Edit >
 * New version. Saving alone does not update the live URL.
 */

/** Tab the rows are appended to. Created automatically when missing. */
var SHEET_NAME = 'Audit Log';

/**
 * Shared secret. A request must carry the same value in its `token` field. Must
 * match DEFAULT_SHEET_TOKEN in scripts/run_audit.py. Leave '' to read it from a
 * Script Property instead.
 */
var SHARED_SECRET = 'report-ads';

/** Script Property consulted when SHARED_SECRET is left empty. */
var SHARED_SECRET_PROPERTY = 'ADS_AUDIT_SHEET_TOKEN';

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
    var sharedSecret = SHARED_SECRET || PropertiesService
      .getScriptProperties()
      .getProperty(SHARED_SECRET_PROPERTY);

    if (!sharedSecret || payload.token !== sharedSecret) {
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
