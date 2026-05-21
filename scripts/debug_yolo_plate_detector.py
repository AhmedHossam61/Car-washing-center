from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug YOLO license plate detection on a recorded video.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("runs/yolo_plate_debug"), type=Path)
    parser.add_argument("--every-n-frames", default=5, type=int)
    parser.add_argument("--max-frames", default=0, type=int)
    parser.add_argument("--confidence", default=0.25, type=float)
    parser.add_argument("--imgsz", default=1280, type=int, help="YOLO inference image size (default 1280; try 1920 for 4K cameras)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    import cv2
    from ultralytics import YOLO

    if not args.video.exists():
        raise FileNotFoundError(f"video not found: {args.video}")
    if not args.weights.exists():
        raise FileNotFoundError(f"weights not found: {args.weights}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = args.output_dir / "crops"
    annotated_dir = args.output_dir / "annotated"
    crops_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "detections.csv"

    model = YOLO(str(args.weights))
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {args.video}")

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["frame_index", "timestamp_ms", "confidence", "x1", "y1", "x2", "y2", "crop_path"],
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
                results = model.predict(frame, conf=args.confidence, imgsz=args.imgsz, verbose=False)
                annotated = frame.copy()

                for result in results:
                    for box_index, box in enumerate(result.boxes):
                        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                        confidence = float(box.conf[0])
                        crop = frame[max(y1, 0) : max(y2, 0), max(x1, 0) : max(x2, 0)]
                        crop_path = crops_dir / f"frame_{frame_index:06d}_{box_index}_{confidence:.2f}.jpg"
                        cv2.imwrite(str(crop_path), crop)

                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(
                            annotated,
                            f"{confidence:.2f}",
                            (x1, max(y1 - 8, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0),
                            2,
                        )
                        writer.writerow(
                            {
                                "frame_index": frame_index,
                                "timestamp_ms": timestamp_ms,
                                "confidence": f"{confidence:.4f}",
                                "x1": x1,
                                "y1": y1,
                                "x2": x2,
                                "y2": y2,
                                "crop_path": str(crop_path),
                            }
                        )
                        detection_count += 1
                        print(f"[frame {frame_index}] conf={confidence:.3f} bbox=({x1},{y1},{x2},{y2})")

                cv2.imwrite(str(annotated_dir / f"frame_{frame_index:06d}.jpg"), annotated)

            frame_index += 1

    cap.release()
    print(f"Processed {frame_index} frames. Plate detections: {detection_count}. CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
