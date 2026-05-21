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

Use Python 3.11 for the OCR environment. PaddleOCR depends on the separate
`paddlepaddle` runtime, and newer Python versions may not have compatible wheels
for every OCR dependency.

To try the PP-OCRv5 mobile Paddle path on top of the current dependency snapshot:

```bash
uv pip uninstall paddlepaddle-gpu paddlepaddle
uv pip install -r requirements-paddle-v5.txt
```

Set `PADDLE_TEXT_RECOGNITION_MODEL_NAME=PP-OCRv5_mobile_rec` to use the selected
PaddleOCR 3.x recognizer on plate crops. On Windows, run the integrated YOLO +
PP-OCRv5 video path with `--cpu-ocr`: YOLO remains on GPU, while Paddle OCR uses
the CPU runtime in the same process.

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

Alternative `fast-alpr` test:

```bash
pip install fast-alpr[onnx]
python scripts/test_fast_alpr_video.py --video test_videos/washing_2.mp4 --every-n-frames 5
```

Results are written to `runs/fast_alpr_video/detections.csv`, with annotated frames
under `runs/fast_alpr_video/annotated/`.

Detector-only debugging with your YOLO plate weights:

```bash
python scripts/debug_yolo_plate_detector.py --video test_videos/washing_2.mp4 --weights models/license-plate-finetune-v1s.pt --every-n-frames 5 --confidence 0.25
```

This writes plate crops and annotated frames under `runs/yolo_plate_debug/`.

OCR crop lab for blurry plate crops:

```bash
python scripts/ocr_crop_lab.py --input-dir runs/yolo_plate_debug/crops --limit 50
```

This writes enhanced crop variants and OCR comparisons under `runs/ocr_crop_lab/`.
The main video pipeline can compare the selected crop-lab variants with
`--preprocess-variant ocr_lab`. Runtime `ocr_lab` currently tries only
`up2_clahe` and `up2_sharp`.

For a full single-camera recorded-video session test, pass the absence timeout:

```bash
python scripts/test_video_pipeline.py --video test_videos/washing_4.mp4 --weights models/license-plate-finetune-v1s.pt --absence-timeout-seconds 120
```

The runner writes confirmed OCR detections to `runs/video_pipeline/detections.csv`
and inferred car sessions to `runs/video_pipeline/sessions.csv`. A session is
completed when its confirmed plate read has been absent longer than the timeout.
