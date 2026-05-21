// Copy the ID from the Sheet URL:
// https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
const SPREADSHEET_ID = "paste-your-spreadsheet-id-here";
const SHEET_NAME = "Sessions";
const WEBHOOK_TOKEN = "change-this-token";

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || "{}");
    if (WEBHOOK_TOKEN && payload.token !== WEBHOOK_TOKEN) {
      return jsonResponse({ ok: false, error: "invalid token" });
    }

    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);
    if (!sheet) {
      throw new Error(`Missing sheet tab: ${SHEET_NAME}`);
    }

    const headers = payload.headers || [];
    const rows = payload.rows || [];
    if (sheet.getLastRow() === 0 && headers.length > 0) {
      sheet.appendRow(headers);
    }
    if (rows.length > 0) {
      sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
    }
    return jsonResponse({ ok: true, appended: rows.length });
  } catch (error) {
    return jsonResponse({ ok: false, error: String(error) });
  }
}

function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
