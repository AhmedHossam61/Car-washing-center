from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection.ocr_engine import OCREngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare OCR results across enhanced plate crop variants.")
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing cropped plate images.")
    parser.add_argument("--output-dir", default=Path("runs/ocr_crop_lab"), type=Path)
    parser.add_argument("--ocr-confidence", default=0.1, type=float)
    parser.add_argument(
        "--ocr-backend",
        default="paddle",
        choices=["paddle", "easyocr", "fastalpr"],
        help="Primary OCR backend.",
    )
    parser.add_argument(
        "--ocr-fallback",
        default="fastalpr",
        choices=["paddle", "easyocr", "fastalpr"],
        help="Fallback backend when primary returns no result.",
    )
    parser.add_argument("--cpu-ocr", action="store_true", help="Disable GPU usage for OCR.")
    parser.add_argument("--limit", default=0, type=int, help="0 means process all images.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    import cv2

    if not args.input_dir.exists():
        raise FileNotFoundError(f"input directory not found: {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = args.output_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "ocr_results.csv"

    image_paths = sorted(
        path for path in args.input_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    )
    if args.limit:
        image_paths = image_paths[: args.limit]

    ocr = OCREngine(
        args.ocr_confidence,
        use_gpu=not args.cpu_ocr,
        backend=args.ocr_backend,
        fallback=args.ocr_fallback,
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["image", "variant", "plate_number", "plate_raw", "confidence", "variant_path"],
        )
        writer.writeheader()

        for image_path in image_paths:
            image = cv2.imread(str(image_path))
            if image is None:
                continue

            for variant_name, variant in enhance_variants(image).items():
                variant_path = variants_dir / f"{image_path.stem}_{variant_name}.jpg"
                cv2.imwrite(str(variant_path), variant)
                try:
                    result = ocr.read(variant)
                except Exception as exc:  # noqa: BLE001
                    print(f"{image_path.name} [{variant_name}] -> OCR error: {exc}")
                    result = None

                row = {
                    "image": str(image_path),
                    "variant": variant_name,
                    "plate_number": "",
                    "plate_raw": "",
                    "confidence": "",
                    "variant_path": str(variant_path),
                }
                if result is not None:
                    row.update(
                        {
                            "plate_number": result.normalized_text,
                            "plate_raw": result.raw_text,
                            "confidence": f"{result.confidence:.4f}",
                        }
                    )
                    print(
                        f"{image_path.name} [{variant_name}] -> "
                        f"{result.normalized_text} raw={result.raw_text!r} conf={result.confidence:.3f}"
                    )
                writer.writerow(row)

    print(f"OCR comparison written to {csv_path}")
    return 0


def enhance_variants(image):
    import cv2

    variants = {"original": image}
    up2 = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    up3 = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    variants["up2"] = up2
    variants["up3"] = up3

    for prefix, source in [("up2", up2), ("up3", up3)]:
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        sharpened = cv2.addWeighted(clahe, 1.6, blur, -0.6, 0)
        adaptive = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
        variants[f"{prefix}_gray"] = gray
        variants[f"{prefix}_clahe"] = clahe
        variants[f"{prefix}_sharp"] = sharpened
        variants[f"{prefix}_adaptive"] = adaptive

    return variants


if __name__ == "__main__":
    raise SystemExit(main())
