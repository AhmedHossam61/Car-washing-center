from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings
from src.detection.confirmation import ConfirmationFilter
from src.detection.ocr_engine import OCREngine
from src.detection.pipeline import ALPRPipeline
from src.detection.plate_detector import PlateDetector
from src.reporting.google_sheets import SheetSessionRow, session_writer_from_settings
from src.session.presence_tracker import PlateObservation, PresenceTracker
from src.utils.image_utils import pad_bbox, preprocess_plate_crop_variant

# Load .env so CLI argument defaults reflect the same values the live server uses.
_settings = Settings()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ALPR pipeline against a recorded video.")
    parser.add_argument("--video", required=True, type=Path, help="Path to a recorded video file.")
    parser.add_argument("--weights", default=_settings.yolo_plate_weights, type=Path)
    parser.add_argument("--output-dir", default=Path("runs/video_pipeline"), type=Path)
    parser.add_argument("--camera-id", default=1, type=int)
    parser.add_argument("--every-n-frames", default=_settings.process_every_n_frames, type=int)
    parser.add_argument("--plate-confidence", default=_settings.plate_confidence, type=float)
    parser.add_argument("--ocr-confidence", default=_settings.ocr_confidence, type=float)
    parser.add_argument(
        "--cpu-ocr",
        action="store_true",
        default=not _settings.ocr_use_gpu,
        help="Disable GPU usage for OCR.",
    )
    parser.add_argument("--imgsz", default=_settings.yolo_imgsz, type=int)
    parser.add_argument("--ocr-backend", default=_settings.ocr_backend, choices=["paddle", "easyocr"])
    parser.add_argument("--ocr-fallback", default=_settings.ocr_fallback, choices=["paddle", "easyocr"])
    parser.add_argument(
        "--preprocess-variant",
        default=_settings.preprocess_variant,
        choices=["current_pipeline", "up2_clahe", "up2_sharp", "up3_clahe", "up3_sharp", "up2_adaptive", "up3_adaptive", "ocr_lab"],
    )
    parser.add_argument("--max-frames", default=0, type=int, help="0 = whole video.")
    parser.add_argument("--min-confirmation-hits", default=_settings.min_confirmation_hits, type=int)
    parser.add_argument("--fuzzy-threshold", default=_settings.confirmation_fuzzy_threshold, type=int)
    parser.add_argument(
        "--session-fuzzy-threshold",
        default=1,
        type=int,
        help="Max plate-key edit distance used to merge confirmed reads into one session.",
    )
    parser.add_argument(
        "--absence-timeout-seconds",
        default=_settings.video_absence_timeout_seconds,
        type=int,
        help="Infer exit after this many seconds without a confirmed plate read.",
    )
    parser.add_argument(
        "--close-active-at-video-end",
        action="store_true",
        help="For recorded-video tests, close remaining active sessions at the video end.",
    )
    parser.add_argument("--debug", action="store_true",
                        help="Enable DEBUG logging and save every YOLO crop to disk for inspection.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import cv2

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s:%(name)s:%(message)s")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = args.output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "detections.csv"
    sessions_csv_path = args.output_dir / "sessions.csv"

    if not args.video.exists():
        raise FileNotFoundError(f"video not found: {args.video}")
    if not args.weights.exists():
        raise FileNotFoundError(f"YOLO weights not found: {args.weights}")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {args.video}")

    pipeline = ALPRPipeline(
        PlateDetector(args.weights, args.plate_confidence, imgsz=args.imgsz),
        OCREngine(args.ocr_confidence, use_gpu=not args.cpu_ocr,
                  backend=args.ocr_backend, fallback=args.ocr_fallback,
                  paddle_text_recognition_model_name=_settings.paddle_text_recognition_model_name),
        detect_width=args.imgsz,
        preprocess_variant=args.preprocess_variant,
    )
    debug_detector = PlateDetector(args.weights, args.plate_confidence, imgsz=args.imgsz) if args.debug else None
    confirmation = ConfirmationFilter(min_hits=args.min_confirmation_hits, fuzzy_threshold=args.fuzzy_threshold)
    presence = PresenceTracker(
        absence_timeout_seconds=args.absence_timeout_seconds,
        fuzzy_threshold=args.session_fuzzy_threshold,
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["frame_index", "timestamp_ms", "plate_number", "arabic_part",
                        "numeric_part", "latin_part", "plate_raw", "confidence", "crop_path"],
        )
        writer.writeheader()

        frame_index = 0
        detection_count = 0
        yolo_crop_count = 0
        ocr_pass_count = 0
        seen_plates: set[str] = set()
        last_video_time = None

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if args.max_frames and frame_index >= args.max_frames:
                break

            if frame_index % args.every_n_frames == 0:
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                video_time = _timestamp_from_video_ms(timestamp_ms)
                last_video_time = video_time
                frame_h, frame_w = frame.shape[:2]

                # Debug mode saves raw crops before OCR, so it needs its own
                # detector pass. Normal runs avoid this duplicate YOLO work.
                raw_hits = debug_detector.detect(frame) if debug_detector is not None else []
                yolo_crop_count += len(raw_hits)
                if raw_hits:
                    print(f"[frame {frame_index}] YOLO: {len(raw_hits)} crop(s) "
                          f"conf=[{', '.join(f'{d.confidence:.2f}' for d in raw_hits)}]")

                if raw_hits:
                    for i, det in enumerate(raw_hits):
                        x1, y1, x2, y2 = pad_bbox(*det.bbox, frame_h=frame_h, frame_w=frame_w)
                        raw_crop = frame[y1:y2, x1:x2]
                        clean = preprocess_plate_crop_variant(raw_crop, args.preprocess_variant)
                        cv2.imwrite(
                            str(crops_dir / f"frame_{frame_index:06d}_det{i}_raw.jpg"),
                            raw_crop,
                        )
                        cv2.imwrite(
                            str(crops_dir / f"frame_{frame_index:06d}_det{i}_preprocessed.jpg"),
                            clean,
                        )

                # ── Full pipeline (OCR + confirmation) ────────────────────
                events = pipeline.process_frame(
                    camera_id=args.camera_id,
                    frame=frame,
                    captured_at=video_time,
                )
                events = confirmation.update(args.camera_id, events)
                ocr_pass_count += len(events)
                presence.update(
                    [
                        PlateObservation(
                            plate_number=event.plate_number,
                            plate_raw=event.plate_raw,
                            seen_at=event.detected_at,
                            confidence=event.confidence,
                            numeric_part=event.numeric_part,
                            latin_part=event.latin_part,
                            arabic_part=event.arabic_part,
                        )
                        for event in events
                    ],
                    video_time,
                )

                for event in events:
                    dedup_key = event.numeric_part or event.plate_number
                    if dedup_key in seen_plates:
                        continue
                    seen_plates.add(dedup_key)

                    crop_path = crops_dir / f"frame_{frame_index:06d}_{event.plate_number}.jpg"
                    cv2.imwrite(str(crop_path), event.crop)
                    writer.writerow({
                        "frame_index": frame_index,
                        "timestamp_ms": int(timestamp_ms),
                        "plate_number": event.plate_number,
                        "arabic_part": event.arabic_part,
                        "numeric_part": event.numeric_part,
                        "latin_part": event.latin_part,
                        "plate_raw": event.plate_raw,
                        "confidence": f"{event.confidence:.4f}",
                        "crop_path": str(crop_path),
                    })
                    detection_count += 1
                    print(f"[frame {frame_index}] {event.plate_number} "
                          f"arabic={event.arabic_part!r} numeric={event.numeric_part!r} "
                          f"latin={event.latin_part!r} conf={event.confidence:.3f}")

            frame_index += 1

    cap.release()
    if args.close_active_at_video_end and last_video_time is not None:
        presence.complete_active(last_video_time)
    presence_sessions = presence.sessions(last_video_time)
    _write_presence_sessions(sessions_csv_path, presence_sessions)
    _append_presence_sessions_to_google_sheet(presence_sessions)
    print(
        f"\nProcessed {frame_index} frames."
        f"\n  Passed OCR + valid plate: {ocr_pass_count}"
        f"\n  Confirmed unique plates : {detection_count}"
        f"\n  CSV: {csv_path}"
        f"\n  Sessions: {sessions_csv_path}"
    )
    if args.debug:
        print(f"  Debug YOLO crops saved  : {yolo_crop_count}")
    _print_presence_sessions(presence_sessions, args.absence_timeout_seconds)
    if args.debug:
        print(f"  Raw + preprocessed crops saved to: {crops_dir}")
    return 0


def _timestamp_from_video_ms(timestamp_ms: float):
    from datetime import datetime, timedelta, timezone
    return datetime.fromtimestamp(0, tz=timezone.utc) + timedelta(milliseconds=timestamp_ms)


def _write_presence_sessions(path: Path, sessions) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "plate_number",
                "numeric_part",
                "latin_part",
                "arabic_part",
                "entry_time_ms",
                "last_seen_ms",
                "inferred_exit_ms",
                "inferred_duration_seconds",
                "visible_duration_seconds",
                "status",
                "observations",
                "confidence",
            ],
        )
        writer.writeheader()
        for session in sessions:
            writer.writerow(
                {
                    "plate_number": session.plate_number,
                    "numeric_part": session.numeric_part,
                    "latin_part": session.latin_part,
                    "arabic_part": session.arabic_part,
                    "entry_time_ms": _video_ms(session.entry_time),
                    "last_seen_ms": _video_ms(session.last_seen_at),
                    "inferred_exit_ms": _video_ms(session.exit_time) if session.exit_time else "",
                    "inferred_duration_seconds": session.inferred_duration_seconds or "",
                    "visible_duration_seconds": session.visible_duration_seconds,
                    "status": session.status,
                    "observations": session.observations,
                    "confidence": f"{session.confidence:.4f}",
                }
            )


def _append_presence_sessions_to_google_sheet(sessions) -> None:
    writer = session_writer_from_settings(_settings)
    if writer is None:
        return
    completed_rows = [
        SheetSessionRow(
            source="recorded_video",
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
        for session in sessions
        if session.status == "completed"
    ]
    appended = writer.append_sessions(completed_rows)
    print(f"  Google Sheet rows added : {appended}")


def _print_presence_sessions(sessions, absence_timeout_seconds: int) -> None:
    print(f"\nPresence sessions (exit after {absence_timeout_seconds}s without plate detection):")
    if not sessions:
        print("  No confirmed plate sessions.")
        return
    for session in sessions:
        inferred_exit = (
            _format_video_time(session.exit_time)
            if session.exit_time is not None
            else "active at video end"
        )
        duration = (
            _format_duration(session.inferred_duration_seconds)
            if session.inferred_duration_seconds is not None
            else "pending"
        )
        print(
            f"  plate={session.plate_number!r} "
            f"entry={_format_video_time(session.entry_time)} "
            f"last_seen={_format_video_time(session.last_seen_at)} "
            f"exit={inferred_exit} duration={duration} "
            f"reads={session.observations} status={session.status}"
        )


def _video_ms(value) -> int:
    return int(value.timestamp() * 1000)


def _format_video_time(value) -> str:
    total_ms = _video_ms(value)
    minutes, remainder = divmod(total_ms, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "pending"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
