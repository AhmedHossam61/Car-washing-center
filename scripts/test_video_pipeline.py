from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

from src.detection.ocr_engine import OCREngine
from src.detection.pipeline import ALPRPipeline
from src.detection.plate_detector import PlateDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ALPR pipeline against a recorded video.")
    parser.add_argument("--video", required=True, type=Path, help="Path to a recorded video file.")
    parser.add_argument("--weights", required=True, type=Path, help="Path to YOLO license plate weights.")
    parser.add_argument("--output-dir", default=Path("runs/video_pipeline"), type=Path)
    parser.add_argument("--camera-id", default=1, type=int)
    parser.add_argument("--every-n-frames", default=5, type=int)
    parser.add_argument("--plate-confidence", default=0.5, type=float)
    parser.add_argument("--ocr-confidence", default=0.70, type=float)
    parser.add_argument("--max-frames", default=0, type=int, help="0 means process the whole video.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = args.output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "detections.csv"

    if not args.video.exists():
        raise FileNotFoundError(f"video not found: {args.video}")
    if not args.weights.exists():
        raise FileNotFoundError(f"YOLO weights not found: {args.weights}")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {args.video}")

    pipeline = ALPRPipeline(
        PlateDetector(args.weights, args.plate_confidence),
        OCREngine(args.ocr_confidence),
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["frame_index", "timestamp_ms", "plate_number", "plate_raw", "confidence", "crop_path"],
        )
        writer.writeheader()

        frame_index = 0
        detection_count = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if args.max_frames and frame_index >= args.max_frames:
                break

            if frame_index % args.every_n_frames == 0:
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                events = pipeline.process_frame(
                    camera_id=args.camera_id,
                    frame=frame,
                    captured_at=_timestamp_from_video_ms(timestamp_ms),
                )
                for event in events:
                    crop_path = crops_dir / f"frame_{frame_index:06d}_{event.plate_number}.jpg"
                    cv2.imwrite(str(crop_path), event.crop)
                    writer.writerow(
                        {
                            "frame_index": frame_index,
                            "timestamp_ms": int(timestamp_ms),
                            "plate_number": event.plate_number,
                            "plate_raw": event.plate_raw,
                            "confidence": f"{event.confidence:.4f}",
                            "crop_path": str(crop_path),
                        }
                    )
                    detection_count += 1
                    print(
                        f"[frame {frame_index}] {event.plate_number} "
                        f"raw={event.plate_raw!r} confidence={event.confidence:.3f}"
                    )

            frame_index += 1

    cap.release()
    print(f"Processed {frame_index} frames. Detections: {detection_count}. CSV: {csv_path}")
    return 0


def _timestamp_from_video_ms(timestamp_ms: float):
    from datetime import datetime, timedelta, timezone

    return datetime.fromtimestamp(0, tz=timezone.utc) + timedelta(milliseconds=timestamp_ms)


if __name__ == "__main__":
    raise SystemExit(main())
