from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.camera.frame_buffer import FrameBuffer
from src.camera.stream import CameraStream
from src.config import CameraConfig, Settings
from src.detection.confirmation import ConfirmationFilter
from src.detection.ocr_engine import OCREngine
from src.detection.pipeline import ALPRPipeline, PlateReadEvent
from src.detection.plate_detector import PlateDetector
from src.reporting.google_sheets import SheetSessionRow, session_writer_from_settings
from src.session.presence_tracker import PlateObservation, PresenceSession, PresenceTracker

logger = logging.getLogger(__name__)
_settings = Settings()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the in-memory one-camera ALPR presence pipeline in real time."
    )
    parser.add_argument("--camera-id", default=1, type=int, help="Camera id from CAMERAS_JSON.")
    parser.add_argument("--weights", default=_settings.yolo_plate_weights, type=Path)
    parser.add_argument("--output-dir", default=Path("runs/camera_pipeline"), type=Path)
    parser.add_argument("--plate-confidence", default=_settings.plate_confidence, type=float)
    parser.add_argument("--ocr-confidence", default=_settings.ocr_confidence, type=float)
    parser.add_argument("--imgsz", default=_settings.yolo_imgsz, type=int)
    parser.add_argument("--every-n-frames", default=_settings.process_every_n_frames, type=int)
    parser.add_argument("--cpu-ocr", action="store_true", default=not _settings.ocr_use_gpu)
    parser.add_argument("--ocr-backend", default=_settings.ocr_backend, choices=["paddle", "easyocr"])
    parser.add_argument("--ocr-fallback", default=_settings.ocr_fallback, choices=["paddle", "easyocr"])
    parser.add_argument(
        "--preprocess-variant",
        default=_settings.preprocess_variant,
        choices=[
            "current_pipeline",
            "up2_clahe",
            "up2_sharp",
            "up3_clahe",
            "up3_sharp",
            "up2_adaptive",
            "up3_adaptive",
            "ocr_lab",
        ],
    )
    parser.add_argument("--min-confirmation-hits", default=_settings.min_confirmation_hits, type=int)
    parser.add_argument("--fuzzy-threshold", default=_settings.confirmation_fuzzy_threshold, type=int)
    parser.add_argument("--session-fuzzy-threshold", default=1, type=int)
    parser.add_argument(
        "--absence-timeout-seconds",
        default=_settings.presence_timeout_minutes * 60,
        type=int,
        help="Close a plate session after this many real-time seconds without a confirmed read.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    )

    camera = _camera_from_settings(args.camera_id)
    if camera.role != "both":
        raise ValueError("run_camera_pipeline expects the selected camera role to be 'both'")
    if not args.weights.exists():
        raise FileNotFoundError(f"YOLO weights not found: {args.weights}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    detections_path = args.output_dir / "detections.csv"
    sessions_path = args.output_dir / "sessions.csv"

    pipeline = ALPRPipeline(
        PlateDetector(args.weights, args.plate_confidence, imgsz=args.imgsz),
        OCREngine(
            args.ocr_confidence,
            use_gpu=not args.cpu_ocr,
            backend=args.ocr_backend,
            fallback=args.ocr_fallback,
            paddle_text_recognition_model_name=_settings.paddle_text_recognition_model_name,
        ),
        detect_width=args.imgsz,
        preprocess_variant=args.preprocess_variant,
    )
    confirmation = ConfirmationFilter(
        min_hits=args.min_confirmation_hits,
        fuzzy_threshold=args.fuzzy_threshold,
    )
    presence = PresenceTracker(
        absence_timeout_seconds=args.absence_timeout_seconds,
        fuzzy_threshold=args.session_fuzzy_threshold,
    )
    sheets_writer = session_writer_from_settings(_settings)

    frame_buffer = FrameBuffer(max_size=4)
    stream = CameraStream(
        camera,
        frame_buffer,
        process_every_n_frames=args.every_n_frames,
    )
    stream.start()
    print(
        f"Watching camera {camera.id} {camera.name!r} in real time."
        f"\n  Session timeout: {args.absence_timeout_seconds}s"
        f"\n  Detections CSV: {detections_path}"
        f"\n  Sessions CSV: {sessions_path}"
        "\nPress Ctrl+C to stop."
    )

    try:
        with detections_path.open("a", newline="", encoding="utf-8") as detections_file, sessions_path.open(
            "a", newline="", encoding="utf-8"
        ) as sessions_file:
            detection_writer = _csv_writer(
                detections_file,
                [
                    "captured_at",
                    "camera_id",
                    "plate_number",
                    "arabic_part",
                    "numeric_part",
                    "latin_part",
                    "plate_raw",
                    "confidence",
                ],
            )
            session_writer = _csv_writer(
                sessions_file,
                [
                    "plate_number",
                    "numeric_part",
                    "latin_part",
                    "arabic_part",
                    "entry_time",
                    "last_seen",
                    "inferred_exit",
                    "inferred_duration_seconds",
                    "visible_duration_seconds",
                    "status",
                    "observations",
                    "confidence",
                ],
            )
            while True:
                now = datetime.now(timezone.utc)
                try:
                    item = frame_buffer.get(timeout=0.5)
                except Empty:
                    confirmation.update(camera.id, [])
                    presence.advance(now)
                    _export_completed_sessions(
                        presence.drain_completed(),
                        session_writer,
                        sessions_file,
                        sheets_writer,
                    )
                    continue

                try:
                    raw_events = pipeline.process_frame(
                        camera_id=item.camera_id,
                        frame=item.frame,
                        captured_at=item.captured_at,
                    )
                except Exception:
                    logger.exception("ALPR pipeline error for camera %d", item.camera_id)
                    presence.advance(item.captured_at)
                    _export_completed_sessions(
                        presence.drain_completed(),
                        session_writer,
                        sessions_file,
                        sheets_writer,
                    )
                    continue
                plate_events = confirmation.update(item.camera_id, raw_events)
                _write_confirmed_detections(detection_writer, detections_file, plate_events)
                presence.update(_observations(plate_events), item.captured_at)
                _export_completed_sessions(
                    presence.drain_completed(),
                    session_writer,
                    sessions_file,
                    sheets_writer,
                )
    except KeyboardInterrupt:
        print("\nStopping camera pipeline.")
    finally:
        stream.stop()
        stream.join(timeout=5)
    return 0


def _camera_from_settings(camera_id: int) -> CameraConfig:
    cameras = [camera for camera in _settings.cameras_json if camera.is_active]
    camera = next((camera for camera in cameras if camera.id == camera_id), None)
    if camera is None:
        raise ValueError(f"active camera id {camera_id} was not found in CAMERAS_JSON")
    return camera


def _csv_writer(csv_file, fieldnames: list[str]) -> csv.DictWriter:
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    if csv_file.tell() == 0:
        writer.writeheader()
        csv_file.flush()
    return writer


def _write_confirmed_detections(
    writer: csv.DictWriter,
    csv_file,
    plate_events: Iterable[PlateReadEvent],
) -> None:
    for event in plate_events:
        writer.writerow(
            {
                "captured_at": event.detected_at.isoformat(),
                "camera_id": event.camera_id,
                "plate_number": event.plate_number,
                "arabic_part": event.arabic_part,
                "numeric_part": event.numeric_part,
                "latin_part": event.latin_part,
                "plate_raw": event.plate_raw,
                "confidence": f"{event.confidence:.4f}",
            }
        )
        print(
            f"[{event.detected_at.isoformat()}] plate={event.plate_number!r} "
            f"arabic={event.arabic_part!r} numeric={event.numeric_part!r} "
            f"latin={event.latin_part!r} conf={event.confidence:.3f}"
        )
    csv_file.flush()


def _observations(plate_events: Iterable[PlateReadEvent]) -> list[PlateObservation]:
    return [
        PlateObservation(
            plate_number=event.plate_number,
            plate_raw=event.plate_raw,
            seen_at=event.detected_at,
            confidence=event.confidence,
            numeric_part=event.numeric_part,
            latin_part=event.latin_part,
            arabic_part=event.arabic_part,
        )
        for event in plate_events
    ]


def _export_completed_sessions(
    sessions: list[PresenceSession],
    csv_writer: csv.DictWriter,
    csv_file,
    sheets_writer,
) -> None:
    if not sessions:
        return

    sheet_rows: list[SheetSessionRow] = []
    for session in sessions:
        csv_writer.writerow(
            {
                "plate_number": session.plate_number,
                "numeric_part": session.numeric_part,
                "latin_part": session.latin_part,
                "arabic_part": session.arabic_part,
                "entry_time": session.entry_time.isoformat(),
                "last_seen": session.last_seen_at.isoformat(),
                "inferred_exit": session.exit_time.isoformat() if session.exit_time else "",
                "inferred_duration_seconds": session.inferred_duration_seconds or "",
                "visible_duration_seconds": session.visible_duration_seconds,
                "status": session.status,
                "observations": session.observations,
                "confidence": f"{session.confidence:.4f}",
            }
        )
        sheet_rows.append(
            SheetSessionRow(
                source="camera",
                plate_number=session.plate_number,
                numeric_part=session.numeric_part,
                latin_part=session.latin_part,
                arabic_part=session.arabic_part,
                entry_time=session.entry_time,
                last_seen_at=session.last_seen_at,
                exit_time=session.exit_time,
                duration_seconds=session.inferred_duration_seconds,
                visible_duration_seconds=session.visible_duration_seconds,
                status=session.status,
                observations=session.observations,
            )
        )
        print(
            f"Session completed: plate={session.plate_number!r} "
            f"entry={session.entry_time.isoformat()} last_seen={session.last_seen_at.isoformat()} "
            f"exit={session.exit_time.isoformat() if session.exit_time else ''} "
            f"duration={session.inferred_duration_seconds}s reads={session.observations}"
        )
    csv_file.flush()

    if sheets_writer is None:
        return
    try:
        appended = sheets_writer.append_sessions(sheet_rows)
        print(f"  Google Sheet rows added : {appended}")
    except Exception:
        logger.exception("Google Sheets upload failed for %d completed session(s)", len(sheet_rows))


if __name__ == "__main__":
    raise SystemExit(main())
