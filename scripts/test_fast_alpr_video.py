from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fast-alpr against a recorded video.")
    parser.add_argument("--video", required=True, type=Path, help="Path to a recorded video file.")
    parser.add_argument("--output-dir", default=Path("runs/fast_alpr_video"), type=Path)
    parser.add_argument("--every-n-frames", default=5, type=int)
    parser.add_argument("--max-frames", default=0, type=int, help="0 means process the whole video.")
    parser.add_argument("--detector-model", default="yolo-v9-t-384-license-plate-end2end")
    parser.add_argument("--ocr-model", default="cct-xs-v2-global-model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import cv2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir = args.output_dir / "annotated"
    annotated_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "detections.csv"

    if not args.video.exists():
        raise FileNotFoundError(f"video not found: {args.video}")

    from fast_alpr import ALPR

    alpr = ALPR(detector_model=args.detector_model, ocr_model=args.ocr_model)
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {args.video}")

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["frame_index", "timestamp_ms", "plate_text", "ocr_confidence", "detection_confidence"],
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
                timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
                results = alpr.predict(frame)
                drawn = alpr.draw_predictions(frame)
                cv2.imwrite(str(annotated_dir / f"frame_{frame_index:06d}.jpg"), drawn.image)

                for result in results:
                    plate_text = _field(result, "ocr.text", "text", default="")
                    ocr_confidence = _field(result, "ocr.confidence", "ocr_confidence", default="")
                    detection_confidence = _field(
                        result,
                        "detection.confidence",
                        "det_confidence",
                        "detection_confidence",
                        default="",
                    )
                    writer.writerow(
                        {
                            "frame_index": frame_index,
                            "timestamp_ms": timestamp_ms,
                            "plate_text": plate_text,
                            "ocr_confidence": ocr_confidence,
                            "detection_confidence": detection_confidence,
                        }
                    )
                    detection_count += 1
                    print(
                        f"[frame {frame_index}] plate={plate_text!r} "
                        f"ocr_conf={ocr_confidence} det_conf={detection_confidence}"
                    )

            frame_index += 1

    cap.release()
    print(f"Processed {frame_index} frames. Detections: {detection_count}. CSV: {csv_path}")
    return 0


def _field(obj: object, *paths: str, default: object = None) -> object:
    for path in paths:
        value = obj
        found = True
        for part in path.split("."):
            if isinstance(value, dict):
                value = value.get(part, default)
            else:
                value = getattr(value, part, default)
            if value is default:
                found = False
                break
        if found:
            return value
    return default


if __name__ == "__main__":
    raise SystemExit(main())
