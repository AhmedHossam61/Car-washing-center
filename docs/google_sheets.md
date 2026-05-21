# Google Sheets Apps Script Output

This project can send completed car-wash sessions to Google Sheets with a small
Apps Script web app. The Python app does not use a Google Cloud service account:
it POSTs rows to the deployed Apps Script URL and includes a shared token that
you choose.

The spreadsheet receives one row per completed session. Repeated OCR reads for
the same active plate are folded into the session `observations` count.

## 1. Prepare The Sheet

1. Create or open the Google spreadsheet that should receive car sessions.
2. Create a tab named `Sessions`.
3. Copy the spreadsheet ID from the browser URL.

For a URL shaped like:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

copy only:

```text
SPREADSHEET_ID
```

The spreadsheet ID selects the Google Sheets file. The Apps Script
`SHEET_NAME` value selects the tab inside that file.

## 2. Create The Apps Script Webhook

1. In the spreadsheet, open Extensions > Apps Script.
2. Replace the editor contents with `docs/google_sheets_app_script.gs`.
3. Fill in the three values at the top of the Apps Script:

```javascript
const SPREADSHEET_ID = "paste-your-spreadsheet-id-here";
const SHEET_NAME = "Sessions";
const WEBHOOK_TOKEN = "choose-a-private-shared-token";
```

`WEBHOOK_TOKEN` is not provided by Google. Choose a private token yourself and
use the exact same value in `.env`.

## 3. Deploy The Web App

Deploy the Apps Script as a web app.

Use these deployment settings:

| Setting | Value |
| --- | --- |
| Execute as | Me |
| Who has access | Anyone |

Copy the **Web app URL** that ends in `/exec`. Use the top Web app URL from the
deployment dialog, not the Library URL.

If you edit the Apps Script later, save it and deploy a new version before
testing the changed behavior.

## 4. Configure `.env`

Set the webhook values in `.env`:

```env
GOOGLE_SHEETS_ENABLED=true
GOOGLE_APPS_SCRIPT_URL=https://script.google.com/macros/s/your_deployment_id/exec
GOOGLE_APPS_SCRIPT_TOKEN=choose-a-private-shared-token
```

The token in `.env` must exactly match `WEBHOOK_TOKEN` in Apps Script.

## 5. Smoke-Test The Webhook

From the project root, send one generated completed session row:

```powershell
uv run python -c "from datetime import datetime, timedelta, timezone; from src.config import Settings; from src.reporting.google_sheets import SheetSessionRow, session_writer_from_settings; now=datetime.now(timezone.utc); writer=session_writer_from_settings(Settings()); row=SheetSessionRow(source='manual_webhook_test', plate_number='TEST 0000', numeric_part='0000', latin_part='TST', arabic_part='TEST', entry_time=now-timedelta(minutes=3), last_seen_at=now-timedelta(seconds=10), exit_time=now, duration_seconds=180, visible_duration_seconds=170, status='completed', observations=1); print('Google Sheet rows added:', writer.append_sessions([row]))"
```

A working webhook prints:

```text
Google Sheet rows added: 1
```

The Sheet should receive a row whose `source` is `manual_webhook_test`.

If the command returns `HTTP Error 401: Unauthorized`, check the web app access
setting first. Python is not signed into a Google account when it POSTs to the
Apps Script URL, so `Who has access` must allow the webhook request.

## 6. Upload From Recorded Video

Recorded-video sessions are uploaded after the run ends. A session normally
uploads only after the plate has been absent longer than the timeout.

For a short test video, keep a realistic timeout and close the active session at
the end of the recording:

```powershell
uv run python scripts\test_video_pipeline.py `
  --video test_videos\washing_9.mp4 `
  --absence-timeout-seconds 30 `
  --close-active-at-video-end
```

Do not use a tiny timeout only to force uploads. If sampled plate reads are
farther apart than that timeout, one real car can be split into many one-read
sessions.

## 7. Upload From The Real-Time Camera

Configure the one camera in `.env` with role `both`:

```env
CAMERAS_JSON=[{"id":1,"name":"Wash Bay","rtsp_url":"rtsp://192.168.1.10:554/stream1","role":"both"}]
```

Run the in-memory camera pipeline:

```powershell
uv run python scripts\run_camera_pipeline.py --camera-id 1
```

The live runner appends one row when a plate session times out. It keeps active
sessions in memory and writes local CSV copies under `runs/camera_pipeline/`.

To test with a live timeout in seconds:

```powershell
uv run python scripts\run_camera_pipeline.py `
  --camera-id 1 `
  --absence-timeout-seconds 60
```

Without the CLI override, the live runner uses `PRESENCE_TIMEOUT_MINUTES` from
`.env`.
