# Smart Car Wash Monitoring System

Foundation implementation for the Saudi car wash monitoring MVP described in
`carwash_monitor_plan.md`.

## Current Status

- FastAPI app skeleton with `/api/v1/health`
- Async SQLAlchemy models and Alembic initial migration
- Config loading from `.env`
- RTSP camera stream manager with reconnect/backoff
- Direct license-plate ALPR pipeline scaffolding for YOLOv11 + OCR
- Session duplicate guard and fuzzy plate matching utilities

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn src.main:app --reload
```

Then open `http://localhost:8000/api/v1/health`.

For Docker:

```bash
docker compose up -d --build
docker compose exec app alembic upgrade head
```

## Test On A Recorded Video

After installing dependencies and placing YOLO license-plate weights locally:

```bash
python scripts/test_video_pipeline.py --video path\to\recording.mp4 --weights models\license_plate_yolov11.pt --every-n-frames 5
```

Results are written to `runs/video_pipeline/detections.csv`, with cropped plate images
under `runs/video_pipeline/crops/`.
