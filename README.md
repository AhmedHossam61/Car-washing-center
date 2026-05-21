# Smart Car Wash Monitoring System

Foundation implementation for the Saudi car wash monitoring MVP described in
`carwash_monitor_plan.md`.

## Current Path

- Config loading from `.env`
- RTSP real-time camera runner with reconnect/backoff
- Recorded-video runner for the same detection/session flow
- Ultralytics YOLO license-plate detection with GPU PyTorch
- PaddleOCR PP-OCRv5 mobile OCR on detected plate crops
- In-memory multi-plate presence tracking for completed wash sessions
- Google Sheets Apps Script output for completed recorded-video and live-camera sessions

## Installation

Use Windows, Python 3.11, `uv`, an NVIDIA driver visible to `nvidia-smi`, and
the license-plate YOLO weights file.

Create the environment and install the pinned dependencies. The extra PyTorch
index is needed for the CUDA `cu128` wheels pinned in `requirements.txt`.

```powershell
uv venv --python 3.11
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128
Copy-Item .env.example .env
```

Place your YOLO plate weights at the path configured in `.env`:

```env
YOLO_PLATE_WEIGHTS=./models/license-plate-finetune-v1s.pt
```

The current integrated Windows pipeline intentionally uses:

- GPU PyTorch for YOLO detection.
- CPU PaddlePaddle for PaddleOCR in the same Python process.
- `PP-OCRv5_mobile_det` and `PP-OCRv5_mobile_rec`; PaddleOCR downloads the model
  files on first use if they are not already cached.

Keep these `.env` OCR settings for that path:

```env
OCR_USE_GPU=false
OCR_BACKEND=paddle
OCR_FALLBACK=paddle
PADDLE_TEXT_RECOGNITION_MODEL_NAME=PP-OCRv5_mobile_rec
```

Check that YOLO can see the GPU and PaddleOCR runtime is installed:

```powershell
uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
uv run python -c "import paddle; print(paddle.__version__); print(paddle.is_compiled_with_cuda())"
```

`torch.cuda.is_available()` should be `True`. `paddle.is_compiled_with_cuda()`
is expected to be `False` for this integrated Windows setup.

## Run On A Recorded Video

The current `.env` defaults match the tuned one-camera recorded-video run:

```powershell
uv run python scripts/test_video_pipeline.py --video test_videos/washing_7.mp4
```

That short command uses the `.env` defaults for the YOLO weights,
`ocr_lab`, Paddle-only CPU OCR, 40-second video absence timeout, every 30th
frame, and `imgsz=1600`. You can still override them explicitly with CLI flags.
Results are written to `runs/video_pipeline/detections.csv`, with cropped plate
images under `runs/video_pipeline/crops/`.

For a full single-camera recorded-video session test with explicit overrides:

```powershell
uv run python scripts/test_video_pipeline.py --video test_videos/washing_7.mp4 --weights models/license-plate-finetune-v1s.pt --preprocess-variant ocr_lab --ocr-backend paddle --ocr-fallback paddle --cpu-ocr --absence-timeout-seconds 40 --every-n-frames 30 --imgsz 1600
```

The runner writes confirmed OCR detections to `runs/video_pipeline/detections.csv`
and inferred car sessions to `runs/video_pipeline/sessions.csv`. A session is
completed when its confirmed plate read has been absent longer than the timeout.

Completed recorded-video and live camera sessions can also be appended to a
Google Sheet through an Apps Script webhook.

## Google Sheets Output

The current MVP can use Google Sheets as the completed-session destination. The
Python app POSTs one row per completed car session to an Apps Script web app; it
does not need a Google Cloud service account.

Follow the setup guide in `docs/google_sheets.md` to:

1. Prepare the `Sessions` spreadsheet tab.
2. Paste and deploy the Apps Script webhook.
3. Configure the spreadsheet ID, shared token, and `.env` URL.
4. Smoke-test the webhook.
5. Upload sessions from recorded video or the real-time camera runner.

## Run One Real-Time Camera

For the current one-camera Google Sheets workflow, use the in-memory camera
runner. It uses the same YOLO/OCR/preprocessing, confirmation, and presence
session logic as the recorded-video runner, and it does not require the database
or FastAPI server.

Set `CAMERAS_JSON` in `.env` with the camera stream URL and `role` set to
`"both"`, then run:

```powershell
uv run python scripts/run_camera_pipeline.py --camera-id 1
```

The `.env` defaults control model weights, `ocr_lab`, Paddle CPU OCR, frame
sampling, and Sheets output. To override the live absence timeout in seconds:

```powershell
uv run python scripts/run_camera_pipeline.py --camera-id 1 --absence-timeout-seconds 60
```

The live runner keeps active plate sessions in memory, supports a few plates
being washed at once, appends one row when each plate session times out, and
writes local CSVs to `runs/camera_pipeline/`.

## Tests And Labs

Run the automated tests:

```powershell
uv run python -B -m pytest tests
```

These files are for testing, debugging, or experiments rather than the main
camera run:

- `tests/`: automated unit tests.
- `test_videos/`: recorded videos used for pipeline testing.
- `scripts/test_video_pipeline.py`: recorded-video pipeline runner and session test harness.
- `scripts/debug_yolo_plate_detector.py`: detector-only plate crop debugging.
- `scripts/ocr_crop_lab.py`: preprocessing and OCR comparison on saved crops.
- `scripts/test_fast_alpr_video.py`: alternative `fast-alpr` experiment.
- `_probe_paddle.py`: older ad hoc Paddle crop probe.

These older test/lab scripts currently contain merge-conflict markers and are
not runnable until repaired or removed:

- `scripts/ocr_comparison.py`
- `scripts/preprocess_variant_lab.py`
- `scripts/test_session_flow.py`

## Future Enhancements If Needed

The current Google Sheets MVP uses the recorded-video runner and the in-memory
one-camera runner. The repository also keeps a database-backed API path for a
larger deployment if it becomes useful later:

- FastAPI startup in `src/main.py` and `src/api/`.
- SQLAlchemy models, migrations, repositories, reports, and session manager in
  `src/db/`, `src/reporting/`, and `src/session/manager.py`.
- The database-backed camera worker in `src/detection/worker.py`.
- Docker and deployment files for the API/database stack.
- A future isolated PaddleOCR GPU worker if CPU OCR becomes the bottleneck on
  the live server.

Before restoring the database-backed path, review its migration files. The
current MVP run path does not use them.
