# Smart Car Wash Monitoring System — Project Plan

**Client:** Saudi Arabia (Freelance)
**Date:** 2026-05-20
**Status:** Planning Phase

---

## Table of Contents

1. [Project Summary](#1-project-summary)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Module Breakdown](#5-module-breakdown)
6. [API Design](#6-api-design)
7. [ALPR Pipeline Design](#7-alpr-pipeline-design)
8. [Multi-Camera Processing](#8-multi-camera-processing)
9. [Session Management Logic](#9-session-management-logic)
10. [Reporting System](#10-reporting-system)
11. [Project Phases & Milestones](#11-project-phases--milestones)
12. [Folder Structure](#12-folder-structure)
13. [Deployment & Setup](#13-deployment--setup)
14. [Risk Assessment](#14-risk-assessment)
15. [Future Enhancements](#15-future-enhancements)

---

## 1. Project Summary

An AI-powered car wash monitoring system that:
- Captures vehicle entry and exit via RTSP/IP cameras
- Automatically reads Saudi license plates (Arabic + English characters)
- Tracks sessions for multiple simultaneous vehicles
- Calculates washing duration per vehicle
- Stores all data and exports Excel/CSV reports

### MVP Scope (Deliverables)

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | AI detection + OCR pipeline | Planned |
| 2 | Multi-camera processing system | Planned |
| 3 | Session management logic | Planned |
| 4 | Backend REST API | Planned |
| 5 | Database integration | Planned |
| 6 | Excel/CSV reporting system | Planned |
| 7 | Deployment/setup documentation | Planned |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CAMERA LAYER                             │
│  [Entrance Cam 1] [Entrance Cam 2] ... [Exit Cam 1] [Exit Cam N]│
│           RTSP / IP Streams                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ RTSP Streams
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  STREAM INGESTION LAYER                         │
│         Camera Manager (per-camera thread / process)            │
│    Frame capture → Frame queue → Frame pre-processing           │
└────────────────────────┬────────────────────────────────────────┘
                         │ Frames
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   AI PROCESSING LAYER                           │
│         ┌───────────────────────────────────────────────┐       │
│         │           ALPR / OCR Engine                   │       │
│         │  License Plate Detector (YOLOv11, LP-tuned)  │       │
│         │  + OCR (PaddleOCR / EasyOCR fallback)        │       │
│         │  Arabic + English support                     │       │
│         └────────────────────┬──────────────────────────┘       │
└──────────────────────────────┼──────────────────────────────────┘
                                           │ Plate text + confidence
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 SESSION MANAGEMENT LAYER                        │
│   Entry Event ──▶ Create Session (plate, timestamp, cam, image) │
│   Exit Event  ──▶ Match Session ──▶ Calculate Duration          │
│                   Duplicate Guard + Confidence Threshold         │
└────────────────────────┬────────────────────────────────────────┘
                         │ Read / Write
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DATABASE LAYER                              │
│              PostgreSQL (primary relational store)              │
│       vehicles | sessions | cameras | events | reports          │
└────────────────────────┬────────────────────────────────────────┘
                         │ ORM / Queries
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API LAYER                            │
│              FastAPI (Python) — REST endpoints                  │
│   /sessions  /cameras  /reports  /events  /health               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   REPORTING LAYER                               │
│         Excel (.xlsx) + CSV export via openpyxl / pandas        │
│    Daily stats | Duration reports | Peak hours | Active sessions│
└─────────────────────────────────────────────────────────────────┘
```

### Component Communication

- Camera threads → AI pipeline via **thread-safe queues**
- AI pipeline → Session manager via **event bus / direct call**
- Session manager → Database via **SQLAlchemy ORM**
- API → Database via **async SQLAlchemy (asyncpg)**
- Reports → File system (exportable on-demand via API)

---

## 3. Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Language | Python 3.11+ | Best AI/CV ecosystem |
| License Plate Detection | YOLOv11 (Ultralytics, LP-pretrained weights) | Latest Ultralytics model — better accuracy/speed than v8; pretrained LP weights available on Roboflow/HuggingFace; no vehicle detection step needed for fixed gate cameras |
| OCR Engine | PaddleOCR (primary) + EasyOCR (fallback) | Both support Arabic script |
| Stream Capture | OpenCV (`cv2.VideoCapture`) | RTSP support, stable |
| Backend API | FastAPI | Async, fast, auto-docs |
| Database | PostgreSQL 15+ | Reliable, concurrent writes |
| ORM | SQLAlchemy 2.0 (async) + Alembic | Modern async ORM |
| Image Storage | Local filesystem (MVP) | Simple, no cloud needed |
| Reporting | pandas + openpyxl | Excel/CSV export |
| Task Queue | Threading / multiprocessing (MVP) | Avoid heavy infra for MVP |
| Config | python-dotenv + Pydantic Settings | Env-based config |
| Logging | Python `logging` + rotating file handler | Operational visibility |
| Deployment | Docker + Docker Compose | Reproducible environment |

---

## 4. Database Schema

### Tables

#### `cameras`
```sql
CREATE TABLE cameras (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    rtsp_url    TEXT NOT NULL,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('entry', 'exit', 'both')),
    location    VARCHAR(200),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

#### `vehicle_sessions`
```sql
CREATE TABLE vehicle_sessions (
    id                  SERIAL PRIMARY KEY,
    plate_number        VARCHAR(50) NOT NULL,        -- normalized plate text
    plate_raw           VARCHAR(100),                -- raw OCR output
    plate_confidence    FLOAT,                       -- OCR confidence 0-1
    entry_time          TIMESTAMPTZ NOT NULL,
    exit_time           TIMESTAMPTZ,
    duration_seconds    INTEGER,                     -- calculated on exit
    entry_camera_id     INTEGER REFERENCES cameras(id),
    exit_camera_id      INTEGER REFERENCES cameras(id),
    entry_snapshot_path TEXT,                        -- path to saved image
    exit_snapshot_path  TEXT,
    status              VARCHAR(20) DEFAULT 'active' -- 'active' | 'completed' | 'manual_close'
        CHECK (status IN ('active', 'completed', 'manual_close')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_plate ON vehicle_sessions (plate_number);
CREATE INDEX idx_sessions_status ON vehicle_sessions (status);
CREATE INDEX idx_sessions_entry_time ON vehicle_sessions (entry_time);
```

#### `detection_events`
```sql
CREATE TABLE detection_events (
    id              SERIAL PRIMARY KEY,
    camera_id       INTEGER REFERENCES cameras(id),
    session_id      INTEGER REFERENCES vehicle_sessions(id),
    event_type      VARCHAR(20) CHECK (event_type IN ('entry', 'exit', 'unknown')),
    plate_number    VARCHAR(50),
    plate_raw       VARCHAR(100),
    confidence      FLOAT,
    snapshot_path   TEXT,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE
);
```

#### `daily_stats` (materialized/computed view or table)
```sql
CREATE TABLE daily_stats (
    id                      SERIAL PRIMARY KEY,
    stat_date               DATE UNIQUE NOT NULL,
    total_vehicles          INTEGER DEFAULT 0,
    completed_sessions      INTEGER DEFAULT 0,
    avg_duration_seconds    FLOAT,
    min_duration_seconds    INTEGER,
    max_duration_seconds    INTEGER,
    peak_hour               INTEGER,                 -- 0-23
    generated_at            TIMESTAMPTZ DEFAULT NOW()
);
```

### Key Design Decisions

- `plate_number` stores a **normalized** version (uppercased, spaces removed, Arabic normalized)
- `plate_raw` stores exactly what OCR returned (for debugging)
- `detection_events` logs every detection; `vehicle_sessions` tracks the matched pair
- Duplicate guard: check if `status = 'active'` session exists for same plate before creating new entry
- Snapshot images stored on local filesystem; DB stores path only

---

## 5. Module Breakdown

### `/src` Directory Modules

```
src/
├── config.py               # All configuration (env vars, camera list, thresholds)
├── main.py                 # Entry point — starts camera workers + API
│
├── camera/
│   ├── manager.py          # CameraManager: starts/stops camera threads
│   ├── stream.py           # CameraStream: reads RTSP, queues frames
│   └── frame_buffer.py     # Thread-safe frame buffer with max-size
│
├── detection/
│   ├── plate_detector.py   # YOLOv11 license plate bounding box (direct, no vehicle step)
│   ├── ocr_engine.py       # PaddleOCR + EasyOCR wrapper, Arabic normalization
│   └── pipeline.py         # End-to-end: frame → plate text + confidence
│
├── session/
│   ├── manager.py          # SessionManager: create, match, close sessions
│   ├── matcher.py          # Plate matching logic (fuzzy match for OCR errors)
│   └── duplicate_guard.py  # Prevents double-entry for same plate
│
├── db/
│   ├── connection.py       # Async SQLAlchemy engine + session factory
│   ├── models.py           # ORM models (Camera, VehicleSession, DetectionEvent)
│   ├── repositories/
│   │   ├── session_repo.py # CRUD for vehicle_sessions
│   │   ├── camera_repo.py  # CRUD for cameras
│   │   └── event_repo.py   # CRUD for detection_events
│   └── migrations/         # Alembic migration files
│
├── api/
│   ├── app.py              # FastAPI app creation + router registration
│   ├── routers/
│   │   ├── sessions.py     # /sessions endpoints
│   │   ├── cameras.py      # /cameras endpoints
│   │   ├── reports.py      # /reports endpoints (triggers export)
│   │   └── health.py       # /health endpoint
│   └── schemas.py          # Pydantic request/response models
│
├── reporting/
│   ├── generator.py        # Builds report DataFrames from DB queries
│   └── exporter.py         # Exports DataFrame to .xlsx / .csv
│
└── utils/
    ├── image_utils.py      # Save snapshot, draw bounding box
    ├── plate_normalizer.py # Arabic/English normalization logic
    └── logger.py           # Logging setup
```

---

## 6. API Design

### Base URL: `http://localhost:8000/api/v1`

#### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions` | List all sessions (filter by status, date, plate) |
| GET | `/sessions/{id}` | Get single session detail |
| GET | `/sessions/active` | All currently active (inside) sessions |
| POST | `/sessions/manual-close/{id}` | Manually close an open session |
| GET | `/sessions/stats/today` | Today's summary stats |

#### Cameras

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cameras` | List all cameras |
| POST | `/cameras` | Register new camera |
| PUT | `/cameras/{id}` | Update camera config |
| DELETE | `/cameras/{id}` | Deactivate camera |
| GET | `/cameras/{id}/status` | Live stream health check |

#### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/daily?date=YYYY-MM-DD` | Daily stats JSON |
| GET | `/reports/export/excel?start=&end=` | Download .xlsx report |
| GET | `/reports/export/csv?start=&end=` | Download .csv report |
| GET | `/reports/peak-hours?date=YYYY-MM-DD` | Hourly vehicle counts |

#### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health (DB, cameras, AI pipeline) |

---

## 7. ALPR Pipeline Design

### Why No Vehicle Detection Step?

Car wash gate cameras are **fixed, controlled environments** — the camera angle is set, and vehicles pass through a defined zone one at a time. Running a general vehicle detector first (YOLO on full-frame for cars/trucks) adds:
- Extra model load and latency
- An unnecessary dependency (if vehicle detector misses, plate is never read)

Instead, we run **YOLOv11 directly on the full frame to find the license plate region**. This is simpler, faster, and equally accurate for a gate scenario. Vehicle detection would only be added if the scene were complex (e.g., parking lots, multi-lane roads).

> **Fallback rule:** If false positives become a problem in testing (e.g., reflective surfaces triggering plate detections), a lightweight vehicle presence check can be added as a pre-filter without restructuring the pipeline.

---

### Pipeline Steps (per frame)

```
Raw Frame
    │
    ▼
[1] License Plate Detection (YOLOv11 — LP pretrained weights)
    - Detect plate bounding box(es) directly in the full frame
    - Pretrained model: e.g. keremberke/license-plate-object-detection (YOLOv8-based)
      or equivalent YOLOv11 LP weights from Roboflow/HuggingFace
    - Filter by confidence threshold (default: 0.5)
    - If no plate found → skip frame, try next
    - If multiple plates in frame → process each independently
    │
    ▼
[2] Plate Image Pre-processing
    - Crop plate bounding box from frame
    - Resize to standard size (e.g., 320×128)
    - Grayscale + contrast enhancement (CLAHE)
    - Perspective correction if skewed
    │
    ▼
[3] OCR — Arabic + English
    - Primary: PaddleOCR (supports Arabic, right-to-left)
    - Fallback: EasyOCR if PaddleOCR confidence < threshold
    - Output: raw text + confidence score
    │
    ▼
[4] Plate Normalization
    - Strip spaces, special chars
    - Normalize Arabic characters (e.g., ا vs أ vs إ)
    - Uppercase Latin characters
    - Standard format: [ARABIC CHARS][LATIN CHARS][DIGITS]
    │
    ▼
[5] Confidence Gate
    - If confidence < 0.70 → discard event
    - If plate < 3 chars → discard
    │
    ▼
[6] Event Emission
    - Emit {plate_number, plate_raw, confidence, camera_id, frame_timestamp, snapshot}
    - → Session Manager
```

### Handling Saudi License Plates

Saudi plates contain:
- Arabic letters (right-to-left region)
- Latin letters (left-to-right region)
- Numbers

**Normalization strategy:**
- Run OCR twice: once right-to-left (Arabic), once left-to-right (Latin/digits)
- Concatenate into canonical form: `AR_CHARS + LAT_CHARS + DIGITS`
- Store normalized form in `plate_number`, raw in `plate_raw`

### OCR Accuracy Strategy

- Use **multi-frame voting**: collect OCR results from 3-5 consecutive frames, pick majority reading
- **Fuzzy matching** for session lookup (Levenshtein distance ≤ 1 for matching)
- Minimum confidence threshold: 0.70 (configurable)
- Store all raw detections in `detection_events` for auditing

---

## 8. Multi-Camera Processing

### Architecture

Each camera runs in its own **daemon thread** (or subprocess for true parallelism):

```python
class CameraStream(threading.Thread):
    def __init__(self, camera_config, frame_queue, ai_pipeline):
        ...
    def run(self):
        cap = cv2.VideoCapture(rtsp_url)
        while self.running:
            ret, frame = cap.read()
            if ret:
                # Process every Nth frame (configurable skip rate)
                if self.frame_count % self.process_every_n == 0:
                    self.frame_queue.put((camera_id, frame, timestamp))
            self.frame_count += 1
```

### Frame Processing

- Each camera queues frames at configurable rate (default: process 1 in every 5 frames = ~6 FPS analysis)
- AI worker threads (configurable pool size) consume from queues
- Separate AI model instance per worker thread (thread-safe)

### Camera Roles

- `entry` cameras → trigger `entry` events → create new sessions
- `exit` cameras → trigger `exit` events → close existing sessions
- `both` cameras → determine direction by motion analysis or config zones

### Connection Resilience

- Auto-reconnect on RTSP stream drop (exponential backoff: 2s, 4s, 8s... max 60s)
- Log disconnection events
- Health endpoint reports per-camera status

---

## 9. Session Management Logic

### Entry Flow

```
Receive entry event {plate, camera_id, timestamp, snapshot}
    │
    ├─ Check duplicate guard:
    │    Is there an active session for this plate?
    │    └─ YES → ignore (already inside), log duplicate detection
    │    └─ NO  → continue
    │
    ├─ Create vehicle_session:
    │    plate_number, entry_time, entry_camera_id,
    │    entry_snapshot_path, status='active'
    │
    └─ Log detection_event (type='entry')
```

### Exit Flow

```
Receive exit event {plate, camera_id, timestamp, snapshot}
    │
    ├─ Find matching active session:
    │    Exact match: SELECT * FROM vehicle_sessions
    │                 WHERE plate_number = :plate AND status = 'active'
    │
    ├─ If no exact match → fuzzy search (Levenshtein distance ≤ 1)
    │
    ├─ If still no match → log as unmatched_exit event, skip
    │
    ├─ If match found:
    │    UPDATE vehicle_sessions SET
    │        exit_time = :timestamp,
    │        exit_camera_id = :camera_id,
    │        exit_snapshot_path = :snapshot,
    │        duration_seconds = EXTRACT(EPOCH FROM exit_time - entry_time),
    │        status = 'completed'
    │
    └─ Log detection_event (type='exit')
```

### Duplicate Guard

- Time-based deduplication: ignore same plate detection within 30 seconds (configurable)
- In-memory LRU cache of recent detections per camera to avoid DB query on every frame

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Car exits without recorded entry | Log as `unmatched_exit`, no session created |
| Same plate detected twice at entry | Ignore second detection (duplicate guard) |
| OCR misreads 1 character | Fuzzy match with Levenshtein ≤ 1 tolerance |
| Session open > 24 hours | Auto-flag as `stale`, manual review required |
| Camera offline at exit | Session stays active; operator can manual-close via API |

---

## 10. Reporting System

### Reports Generated

| Report | Content | Format |
|--------|---------|--------|
| Daily Summary | Total vehicles, completed, active, avg/min/max duration | Excel + CSV |
| Session Detail | Full record of all sessions in date range | Excel + CSV |
| Peak Hours | Hourly vehicle count for a given day | Excel |
| Duration Distribution | Histogram data of washing durations | Excel |
| Active Sessions | Currently inside vehicles (real-time snapshot) | JSON + Excel |
| Operational Stats | Longest/shortest wash, daily trends | Excel |

### Excel Report Structure (Daily Summary)

**Sheet 1: Summary**
| Field | Value |
|-------|-------|
| Report Date | 2026-05-20 |
| Total Vehicles | 87 |
| Completed Sessions | 84 |
| Active Now | 3 |
| Avg Duration | 18 min 42 sec |
| Fastest Wash | 8 min 10 sec |
| Longest Wash | 45 min 2 sec |
| Peak Hour | 10:00 - 11:00 (23 vehicles) |

**Sheet 2: Session Details**
| Plate | Entry Time | Exit Time | Duration | Entry Cam | Exit Cam | Status |
|-------|-----------|-----------|----------|-----------|----------|--------|
| ...   | ...       | ...       | ...      | ...       | ...      | ...    |

**Sheet 3: Hourly Breakdown**
| Hour | Vehicle Count |
|------|--------------|
| 08:00 | 5 |
| 09:00 | 12 |
| ... | ... |

### Export API

```
GET /api/v1/reports/export/excel?start=2026-05-20&end=2026-05-20
→ Returns: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
→ Filename: carwash_report_2026-05-20.xlsx
```

---

## 11. Project Phases & Milestones

### Phase 1 — Foundation & Infrastructure (Week 1-2)

**Goal:** Working skeleton with database, config, and camera connection

- [ ] Set up project structure and virtual environment
- [ ] Configure Docker Compose (Python app + PostgreSQL)
- [ ] Implement `config.py` with all env-var settings
- [ ] Create database models (SQLAlchemy) and run Alembic migrations
- [ ] Implement repository layer (CRUD operations)
- [ ] Build camera stream class with RTSP connection + auto-reconnect
- [ ] Build camera manager to handle multiple streams
- [ ] Write `/health` API endpoint

**Deliverable:** System connects to cameras and DB, health check passes

---

### Phase 2 — AI Detection Pipeline (Week 2-3)

**Goal:** Working ALPR on single camera

- [ ] Source pretrained YOLOv11 LP detection weights (Roboflow universe or HuggingFace — e.g. `keremberke/license-plate-object-detection` ported to v11, or train on a Saudi plate dataset)
- [ ] Integrate YOLOv11 plate detector (direct full-frame detection, no vehicle step)
- [ ] Integrate PaddleOCR with Arabic language support
- [ ] Integrate EasyOCR as fallback
- [ ] Implement plate normalization (Arabic + English + digits)
- [ ] Implement multi-frame voting for OCR accuracy
- [ ] Test on sample Saudi plate images (offline)
- [ ] Test on live RTSP stream (single camera)
- [ ] Tune confidence thresholds; add vehicle-presence pre-filter only if false positives are observed

**Deliverable:** System reads Saudi license plates from live camera feed with >85% accuracy

---

### Phase 3 — Session Management (Week 3-4)

**Goal:** Full entry/exit session tracking for multiple vehicles

- [ ] Implement SessionManager (entry + exit flows)
- [ ] Implement duplicate guard (in-memory + DB check)
- [ ] Implement fuzzy plate matching (Levenshtein)
- [ ] Connect AI pipeline events to SessionManager
- [ ] Snapshot saving (entry/exit images to filesystem)
- [ ] Test multi-vehicle simultaneous tracking
- [ ] Handle edge cases (unmatched exits, stale sessions, OCR errors)

**Deliverable:** System correctly tracks 5+ simultaneous vehicles through entry and exit

---

### Phase 4 — Multi-Camera Integration (Week 4-5)

**Goal:** Stable processing across all cameras simultaneously

- [ ] Extend CameraManager for N cameras
- [ ] Camera role assignment (entry/exit/both) from config
- [ ] Per-camera frame queues and AI worker pools
- [ ] Test with 2+ cameras simultaneously
- [ ] Validate session matching across different cameras
- [ ] Stress test with high vehicle volume simulation

**Deliverable:** All cameras operational simultaneously, no dropped sessions

---

### Phase 5 — Backend API (Week 5-6)

**Goal:** Full REST API for all operations

- [ ] Implement `/sessions` endpoints (list, detail, active, manual-close)
- [ ] Implement `/cameras` endpoints (CRUD, status)
- [ ] Implement `/reports` endpoints (daily stats, export triggers)
- [ ] Implement request/response Pydantic schemas
- [ ] Add pagination, filtering, date range queries
- [ ] API documentation (FastAPI auto-generates Swagger/OpenAPI)
- [ ] Basic API authentication (API key header for MVP)

**Deliverable:** All API endpoints functional and documented

---

### Phase 6 — Reporting System (Week 6-7)

**Goal:** Full Excel/CSV reporting

- [ ] Implement report data queries (daily summary, session detail, hourly breakdown)
- [ ] Build Excel report generator (openpyxl, multi-sheet)
- [ ] Build CSV exporter
- [ ] Wire up report download endpoints
- [ ] Test report accuracy against known data
- [ ] Style Excel reports (headers, column widths, formatting)

**Deliverable:** All 6 report types downloadable via API in Excel and CSV

---

### Phase 7 — Testing, Hardening & Docs (Week 7-8)

**Goal:** Production-ready, documented system

- [ ] End-to-end integration test (entry → session → exit → report)
- [ ] Load test (simulate 10 vehicles/hour over 8 hours)
- [ ] Error handling and graceful shutdown
- [ ] Log rotation and log level configuration
- [ ] Environment variable documentation (.env.example)
- [ ] Write deployment/setup guide (Docker + manual)
- [ ] Write camera configuration guide
- [ ] Write API reference documentation
- [ ] Code review and cleanup

**Deliverable:** Deployable system with full documentation

---

### Timeline Summary

| Phase | Duration | Week |
|-------|----------|------|
| 1. Foundation | 2 weeks | 1-2 |
| 2. AI Pipeline | 1.5 weeks | 2-3 |
| 3. Session Management | 1 week | 3-4 |
| 4. Multi-Camera | 1 week | 4-5 |
| 5. Backend API | 1 week | 5-6 |
| 6. Reporting | 1 week | 6-7 |
| 7. Testing & Docs | 1 week | 7-8 |
| **Total** | **~8 weeks** | |

---

## 12. Folder Structure

```
carwash-monitor/
├── .env.example                    # Environment variable template
├── .env                            # Actual env vars (gitignored)
├── docker-compose.yml              # App + PostgreSQL services
├── Dockerfile                      # Python app container
├── requirements.txt
├── alembic.ini
├── README.md
│
├── src/
│   ├── main.py                     # Entry point
│   ├── config.py                   # Settings via pydantic-settings
│   │
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── stream.py
│   │   └── frame_buffer.py
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── plate_detector.py
│   │   ├── ocr_engine.py
│   │   └── pipeline.py
│   │
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── matcher.py
│   │   └── duplicate_guard.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── models.py
│   │   ├── repositories/
│   │   │   ├── session_repo.py
│   │   │   ├── camera_repo.py
│   │   │   └── event_repo.py
│   │   └── migrations/
│   │       └── versions/
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       ├── sessions.py
│   │       ├── cameras.py
│   │       ├── reports.py
│   │       └── health.py
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── generator.py
│   │   └── exporter.py
│   │
│   └── utils/
│       ├── image_utils.py
│       ├── plate_normalizer.py
│       └── logger.py
│
├── snapshots/                      # Saved vehicle images (gitignored)
│   ├── entry/
│   └── exit/
│
├── reports/                        # Generated report files (gitignored)
│
├── tests/
│   ├── test_ocr.py
│   ├── test_session_manager.py
│   ├── test_plate_normalizer.py
│   ├── test_api.py
│   └── sample_plates/              # Test plate images
│
└── docs/
    ├── deployment.md
    ├── camera_setup.md
    └── api_reference.md
```

---

## 13. Deployment & Setup

### Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.9'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: carwash
      POSTGRES_USER: carwash_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  app:
    build: .
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://carwash_user:${DB_PASSWORD}@db/carwash
      CAMERAS: ${CAMERAS_JSON}
      SNAPSHOT_DIR: /app/snapshots
      REPORT_DIR: /app/reports
    volumes:
      - ./snapshots:/app/snapshots
      - ./reports:/app/reports
    ports:
      - "8000:8000"
    restart: unless-stopped

volumes:
  pgdata:
```

### Environment Variables (`.env.example`)

```bash
# Database
DB_PASSWORD=your_secure_password

# Camera configuration (JSON array)
# role: "entry" | "exit" | "both"
CAMERAS_JSON='[
  {"id": 1, "name": "Entry Gate 1", "rtsp_url": "rtsp://192.168.1.10:554/stream1", "role": "entry"},
  {"id": 2, "name": "Exit Gate 1",  "rtsp_url": "rtsp://192.168.1.11:554/stream1", "role": "exit"}
]'

# AI Thresholds
PLATE_CONFIDENCE=0.5
OCR_CONFIDENCE=0.70
DUPLICATE_GUARD_SECONDS=30
PROCESS_EVERY_N_FRAMES=5

# Storage
SNAPSHOT_DIR=./snapshots
REPORT_DIR=./reports

# API
API_KEY=your_api_key_here
API_PORT=8000

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/carwash.log
```

### Quick Start

```bash
# 1. Clone and enter project
git clone <repo>
cd carwash-monitor

# 2. Copy env template
cp .env.example .env
# Edit .env with your camera IPs and passwords

# 3. Start services
docker-compose up -d

# 4. Run DB migrations
docker-compose exec app alembic upgrade head

# 5. Verify
curl http://localhost:8000/api/v1/health
```

---

## 14. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OCR misreads Arabic characters | High | High | Multi-frame voting, fuzzy matching, confidence threshold, PaddleOCR + EasyOCR dual engine |
| RTSP stream drops | Medium | Medium | Auto-reconnect with backoff, health monitoring |
| Multiple plates in same frame | Low | Medium | YOLOv11 returns all bounding boxes; process each independently; gate cameras rarely have 2 cars in frame simultaneously |
| False plate detection (non-plate region) | Low | Low | Confidence threshold (0.5+) filters most; add vehicle presence pre-filter only if needed in testing |
| License plate partially obscured | High | Medium | Retry on next frames, multi-frame voting |
| Same plate detected as new entry after exit | Low | High | Time-based duplicate guard (30s window) |
| High CPU load from multiple cameras | Medium | Medium | Frame skip rate, configurable worker pool, GPU acceleration (if available) |
| Session left open (car never exits) | Medium | Low | 24h stale session flag, manual close API |
| Unmatched exit (OCR error on exit) | Medium | Medium | Fuzzy match ≤1 char, log for manual review |
| Database connection failure | Low | High | SQLAlchemy connection pooling, retry logic |

---

## 15. Future Enhancements

> Not in MVP scope — documented for future development phases

| Enhancement | Description | Priority |
|------------|-------------|----------|
| Web Dashboard | React/Vue frontend showing live sessions, camera feeds, stats | High |
| Live Video Feed | WebSocket/HLS stream viewer in dashboard | High |
| Multi-Branch Support | Branch ID field on all tables, branch-level reporting | Medium |
| Cloud Deployment | AWS/Azure deployment with managed DB, S3 for images | Medium |
| Worker Performance Analysis | Track which operator handled each vehicle | Medium |
| Mobile Alerts | SMS/WhatsApp notifications for anomalies | Low |
| Advanced Analytics | ML-based peak prediction, anomaly detection | Low |
| Payment Integration | Link washing duration to billing/POS system | Low |
| GPU Acceleration | CUDA-based inference for higher throughput | Medium |
| Arabic Web UI | RTL dashboard fully in Arabic | Medium |

---

*Plan authored: 2026-05-20*
*Project: Smart Car Wash Monitoring System — Saudi Arabia Client*
