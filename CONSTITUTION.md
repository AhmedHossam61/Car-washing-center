# Car Wash Center — Project Constitution

## 1. Purpose

An automated vehicle monitoring system for car wash centers. It reads Saudi license plates from RTSP camera streams in real time, records vehicle entry/exit sessions with timestamps, and exposes a REST API for management and reporting.

---

## 2. Core Client Requirement: Entry / Exit Log

Every vehicle that passes through must be logged as:

```
Car 3327 HGJ  entered  at  2026-05-21 09:14:32
Car 3327 HGJ  exited   at  2026-05-21 09:27:55   (duration: 00:13:23)
```

### Is this already implemented? ✅ Yes — fully.

| What the client needs | Where it is stored | How to access it |
|-----------------------|--------------------|-----------------|
| Plate number          | `vehicle_sessions.plate_number` | `GET /sessions` |
| Entry timestamp       | `vehicle_sessions.entry_time`   | `GET /sessions` |
| Exit timestamp        | `vehicle_sessions.exit_time`    | `GET /sessions` |
| Duration              | `vehicle_sessions.duration_seconds` + `duration_formatted` (HH:MM:SS) | `GET /sessions` |
| Status                | `vehicle_sessions.status` → `active` / `completed` / `manual_close` | `GET /sessions` |
| Entry snapshot photo  | `vehicle_sessions.entry_snapshot_path` | file path on disk |
| Exit snapshot photo   | `vehicle_sessions.exit_snapshot_path`  | file path on disk |

### Example API response (`GET /sessions/42`)

```json
{
  "id": 42,
  "plate_number": "هقح 3327 HGJ",
  "plate_raw": "MY 3327HGJ",
  "plate_confidence": 0.71,
  "entry_time": "2026-05-21T09:14:32Z",
  "exit_time": "2026-05-21T09:27:55Z",
  "duration_seconds": 803,
  "duration_formatted": "00:13:23",
  "status": "completed",
  "entry_camera_id": 1,
  "exit_camera_id": 2,
  "entry_snapshot_path": "./snapshots/entry/20260521_091432_3327HGJ.jpg",
  "exit_snapshot_path": "./snapshots/exit/20260521_092755_3327HGJ.jpg",
  "created_at": "2026-05-21T09:14:32Z"
}
```

### Daily report (`GET /reports/daily` or exported as CSV)

Returns a summary for a given day: total vehicles, completed sessions, average duration, busiest hour.

---

## 2. Saudi License Plate Format

Saudi plates have two rows:

```
┌──────────────────┐
│   ه  ق  ح        │  ← Top row: 3 Arabic letters
│   3327  HGJ      │  ← Bottom row: exactly 4 digits + exactly 3 Latin letters
└──────────────────┘
```

### Validation Rules (enforced in `src/utils/plate_normalizer.py`)

| Field        | Rule                          | Example  |
|--------------|-------------------------------|----------|
| Digits       | Exactly **4** digits          | `3327`   |
| Latin        | Exactly **3** uppercase letters from the allowed 17 | `HGJ` |
| Arabic       | Derived deterministically from Latin via `ENG_TO_ARABIC` mapping | `هقح` |

Any OCR reading that does not satisfy exactly 4 digits **and** exactly 3 Latin letters is rejected (`is_valid=False`) before it enters the session pipeline.

### Allowed Latin ↔ Arabic Mapping (`ENG_TO_ARABIC`)

| Latin | Arabic | | Latin | Arabic | | Latin | Arabic |
|-------|--------|-|-------|--------|-|-------|--------|
| A     | ا      | | J     | ح      | | N     | ن      |
| B     | ب      | | K     | ك      | | H     | ه      |
| D     | د      | | L     | ل      | | V     | و      |
| E     | ع      | | M     | م      | | X     | ص      |
| G     | ق      | | R     | ر      | | Y     | ى      |
| S     | س      | | T     | ط      | |       |        |

---

## 3. Architecture

```
RTSP Cameras
     │
     ▼
CameraManager (stream.py / manager.py)
     │  frames
     ▼
FrameBuffer (frame_buffer.py)
     │
     ▼
AIWorker (worker.py)
     │
     ├─► PlateDetector  (YOLO ultralytics)
     │         │ bounding boxes
     │         ▼
     │   preprocess_plate_crop()   ← image enhancement
     │         │
     │         ▼
     │   OCREngine  (ocr_engine.py)
     │         │  OCRResult (raw_text, digits, latin, arabic, confidence)
     │         ▼
     │   ConfirmationFilter  (confirmation.py)
     │         │  confirmed events only
     │         ▼
     └─► SessionManager  (session/manager.py)
               │
               ├─► DuplicateGuard
               └─► SessionRepository  (PostgreSQL via asyncpg)

FastAPI  ──► REST API (sessions, cameras, reports, health)
```

---

## 4. Detection Pipeline Detail

### 4a. Image Pre-processing (`src/utils/image_utils.py`)

Applied to every YOLO crop before OCR:

1. **Upscale** — resize to minimum 128 px height using `INTER_CUBIC`
2. **Grayscale** — convert to single channel
3. **Denoising** — `fastNlMeansDenoising(h=10)` removes RTSP/H.264 compression artefacts
4. **CLAHE** — `clipLimit=2.0, tileGridSize=(8,8)` normalises local contrast under harsh car-wash lighting
5. **Unsharp Mask** — `1.6 × original − 0.6 × blurred` sharpens motion-blurred character edges
6. **Back to BGR** — convert back to 3-channel so all OCR backends receive a standard image

### 4b. OCR Backends (`src/detection/ocr_engine.py`)

Controlled via `.env` — no code changes needed to switch:

| Backend     | `.env` value | Description |
|-------------|--------------|-------------|
| PaddleOCR   | `paddle`     | Best accuracy on Saudi plates. **Recommended primary.** |
| EasyOCR     | `easyocr`    | Arabic-aware; can hallucinate on some plate fonts |
| fast-alpr   | `fastalpr`   | End-to-end detector+OCR; fastest but lowest accuracy |

Primary runs first. Fallback runs only if primary returns nothing.
Set `OCR_FALLBACK` to the same value as `OCR_BACKEND` to disable fallback.

### 4c. Confirmation Filter (`src/detection/confirmation.py`)

Prevents noisy single-frame detections from creating false sessions.

- All OCR readings are **grouped by fuzzy similarity** (Levenshtein distance ≤ `CONFIRMATION_FUZZY_THRESHOLD`). Variants like `3327`, `3307`, `337` all land in the same cluster.
- Once a cluster accumulates `MIN_CONFIRMATION_HITS` total readings, it is **confirmed**.
- The emitted plate uses **majority vote** for both digits and Latin letters across all readings in the cluster.
- The cluster is cleared the moment the plate disappears from the frame.

---

## 5. Session Logic

### Camera Roles

| Role    | Behaviour |
|---------|-----------|
| `entry` | First detection of a plate → open new session |
| `exit`  | Detection of a plate → close matching active session |
| `both`  | First detection → open session; re-detections → update `last_seen_at`; session auto-closes after `PRESENCE_TIMEOUT_MINUTES` of no detection |

### Plate Matching

Sessions are looked up by **digits only** (e.g. `3327`), not the full plate string. The DB query uses `LIKE %3327%` so minor OCR variations in the letter suffix never fragment a session.

### Duplicate Guard

Within `DUPLICATE_GUARD_SECONDS` of an entry event for the same plate, subsequent entry events are silently dropped to prevent duplicate sessions from fast re-detections.

### Session Statuses

| Status         | Meaning |
|----------------|---------|
| `active`       | Vehicle is inside |
| `completed`    | Vehicle exited (exit camera matched or presence timeout) |
| `manual_close` | Closed via the API |

---

## 6. REST API

Base URL: `http://host:API_PORT`  
Authentication: `X-API-Key: <API_KEY>` header required on all routes except `/health`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/health` | System health (DB + cameras) |
| GET    | `/cameras` | List cameras with live status |
| GET    | `/sessions` | List sessions (filters: `status`, `plate`, `limit`, `offset`) |
| GET    | `/sessions/active` | Active sessions only |
| GET    | `/sessions/stats` | Aggregated counts |
| GET    | `/sessions/{id}` | Single session |
| POST   | `/sessions/{id}/close` | Manually close a session |
| GET    | `/reports/daily` | Daily summary JSON |
| GET    | `/reports/daily/export` | Daily summary as CSV download |

---

## 7. Database Schema

### `cameras`

| Column      | Type         | Notes |
|-------------|--------------|-------|
| id          | INTEGER PK   |       |
| name        | VARCHAR(100) |       |
| rtsp_url    | TEXT         |       |
| role        | VARCHAR(20)  | `entry` \| `exit` \| `both` |
| location    | VARCHAR(200) | nullable |
| is_active   | BOOLEAN      | default true |
| created_at  | TIMESTAMPTZ  | server default |

### `vehicle_sessions`

| Column               | Type         | Notes |
|----------------------|--------------|-------|
| id                   | INTEGER PK   |       |
| plate_number         | VARCHAR(50)  | canonical form e.g. `هقح 3327 HGJ` |
| plate_raw            | VARCHAR(100) | raw OCR text |
| plate_confidence     | FLOAT        |       |
| entry_time           | TIMESTAMPTZ  |       |
| exit_time            | TIMESTAMPTZ  | nullable |
| duration_seconds     | INTEGER      | nullable |
| entry_camera_id      | FK cameras   | nullable |
| exit_camera_id       | FK cameras   | nullable |
| entry_snapshot_path  | TEXT         | nullable |
| exit_snapshot_path   | TEXT         | nullable |
| status               | VARCHAR(20)  | `active` \| `completed` \| `manual_close` |
| last_seen_at         | TIMESTAMPTZ  | updated on each re-detection (single-camera mode) |
| created_at           | TIMESTAMPTZ  | server default |
| updated_at           | TIMESTAMPTZ  | auto-updated on change |

**Indexes:** `plate_number`, `status`, `entry_time`

---

## 8. Configuration Reference (`.env`)

```ini
# ── Database ──────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://carwash_user:password@localhost:5432/carwash

# ── Cameras ───────────────────────────────────────────────────────────────
# role: "entry" | "exit" | "both"
CAMERAS_JSON=[{"id":1,"name":"Entry Gate","rtsp_url":"rtsp://...","role":"entry"},
              {"id":2,"name":"Exit Gate","rtsp_url":"rtsp://...","role":"exit"}]

# ── Detection thresholds ──────────────────────────────────────────────────
PLATE_CONFIDENCE=0.5            # YOLO minimum box confidence (0.0–1.0)
OCR_CONFIDENCE=0.70             # Minimum OCR confidence to accept a reading
OCR_USE_GPU=true                # Use GPU for OCR (false → CPU)
OCR_BACKEND=paddle              # Primary OCR: paddle | easyocr | fastalpr
OCR_FALLBACK=fastalpr           # Fallback OCR (same as backend = no fallback)
YOLO_PLATE_WEIGHTS=./models/license-plate-finetune-v1s.pt

# ── Confirmation filter ───────────────────────────────────────────────────
MIN_CONFIRMATION_HITS=3         # Frames a plate must appear before being recorded
CONFIRMATION_FUZZY_THRESHOLD=2  # Max Levenshtein distance to group OCR variants

# ── Session behaviour ─────────────────────────────────────────────────────
DUPLICATE_GUARD_SECONDS=30      # Min gap between two entry events for the same plate
PROCESS_EVERY_N_FRAMES=5        # Sample 1 frame out of every N from the stream
AI_WORKER_COUNT=1               # Parallel AI worker threads
PRESENCE_TIMEOUT_MINUTES=5      # "both"-role session auto-close timeout

# ── Storage ───────────────────────────────────────────────────────────────
SNAPSHOT_DIR=./snapshots
REPORT_DIR=./reports

# ── API ───────────────────────────────────────────────────────────────────
API_KEY=your_secret_key
API_PORT=8000

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL=INFO                  # DEBUG | INFO | WARNING | ERROR
LOG_FILE=./logs/carwash.log
```

---

## 9. Running the Project

### Prerequisites

- Python 3.11+
- `uv` package manager
- PostgreSQL 14+
- NVIDIA GPU + CUDA (optional but recommended)

### Setup

```powershell
# Install dependencies
uv sync

# Copy and configure environment
copy .env.example .env
# Edit .env with your database URL, camera URLs, and API key

# Run database migrations
uv run alembic upgrade head

# Start the API server
uv run python -m src.main
```

### Test Script (offline video)

```powershell
uv run python scripts/test_video_pipeline.py --video test_videos/your_video.mp4

# Override specific settings without editing .env:
uv run python scripts/test_video_pipeline.py \
  --video test_videos/washing_3.mp4 \
  --ocr-backend paddle \
  --ocr-fallback fastalpr \
  --min-confirmation-hits 4 \
  --fuzzy-threshold 2
```

### Docker

```powershell
docker-compose up --build
```

---

## 10. Project Structure

```
src/
├── config.py              # All settings (loaded from .env)
├── main.py                # FastAPI app entry point
├── api/                   # REST API routers and schemas
├── camera/                # RTSP stream reader and frame buffer
├── db/                    # SQLAlchemy models, repositories, migrations
├── detection/
│   ├── plate_detector.py  # YOLO wrapper
│   ├── ocr_engine.py      # PaddleOCR / EasyOCR / fast-alpr backends
│   ├── pipeline.py        # Connects detector → OCR → PlateReadEvent
│   ├── confirmation.py    # Fuzzy confirmation filter
│   └── worker.py          # Async AI worker loop
├── session/               # Session open/close logic and duplicate guard
├── reporting/             # Daily summary generator and CSV exporter
└── utils/
    ├── image_utils.py     # Plate crop pre-processing
    ├── plate_normalizer.py # Saudi plate parsing and Latin→Arabic mapping
    └── logger.py          # Logging configuration

scripts/
├── test_video_pipeline.py  # Offline video test (writes detections.csv)
└── ocr_comparison.py       # Compare OCR backends on saved crop images

models/                     # YOLO .pt weight files
docs/                       # API reference, camera setup, deployment guide
```

---

## 11. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Digits-only session keying | OCR produces variant letter suffixes (`HGJ` vs `HG`) per frame; digits are more stable |
| Fuzzy cluster confirmation | Single-frame OCR noise on digit `2` (reads as `0`, `3`, `8`, etc.) would reset a streak counter; clustering tolerates it |
| Majority vote on confirmed plate | Most-seen reading across N frames wins, not the last frame's reading |
| Deterministic Latin→Arabic mapping | EasyOCR hallucinated different Arabic letters every frame on Saudi plate fonts; mapping from Latin is stable |
| PaddleOCR as default primary | Empirically most accurate on Saudi plates in testing; no DLL conflict with PyTorch on Windows |
| Lazy OCR model loading | Only the selected backend(s) are loaded into memory at runtime |
