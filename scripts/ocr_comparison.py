"""Compare three OCR backends on existing plate crop images.

Approaches
----------
1. EasyOCR  — English reader with Saudi-plate allowlist
2. PaddleOCR — English; skipped automatically if DLL conflict detected on Windows
3. fast-plate-ocr (cct-xs-v2-global-model) — the current production backend

Usage
-----
    uv run python scripts/ocr_comparison.py --crops-dir runs/video_pipeline/crops

Optional flags
    --crops-dir   DIR    Directory of .jpg/.png plate crop images (default: runs/video_pipeline/crops)
    --max-images  N      Limit to first N images (0 = all, default: 20)
    --output      FILE   Write results to CSV (default: runs/ocr_comparison/results.csv)
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SAUDI_ALLOWLIST = "ABDJRSXTEGKLMNHVY0123456789"


# ---------------------------------------------------------------------------
# Backend wrappers — each returns (text: str, latency_ms: float)
# ---------------------------------------------------------------------------

def run_easyocr(image_bgr: np.ndarray, reader) -> tuple[str, float]:
    t0 = time.perf_counter()
    results = reader.readtext(image_bgr, allowlist=SAUDI_ALLOWLIST, detail=0)
    ms = (time.perf_counter() - t0) * 1000
    return "".join(results).strip(), ms


def run_paddle(image_bgr: np.ndarray, ocr) -> tuple[str, float]:
    t0 = time.perf_counter()
    result = ocr.ocr(image_bgr, cls=False)
    ms = (time.perf_counter() - t0) * 1000
    texts: list[str] = []
    if result and result[0]:
        for line in result[0]:
            texts.append(line[1][0])
    return " ".join(texts).strip(), ms


def run_fast_plate_ocr(image_bgr: np.ndarray, recognizer) -> tuple[str, float]:
    t0 = time.perf_counter()
    preds = recognizer.run(image_bgr)
    ms = (time.perf_counter() - t0) * 1000
    text = preds[0].plate if preds else ""
    return text.strip(), ms


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_easyocr():
    print("Loading EasyOCR (en)…")
    import easyocr
    return easyocr.Reader(["en"], gpu=True)


def load_paddle():
    print("Loading PaddleOCR (en)…")
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang="en", show_log=False, use_angle_cls=False)
        # warm-up probe
        dummy = np.zeros((64, 128, 3), dtype=np.uint8)
        ocr.ocr(dummy, cls=False)
        return ocr
    except Exception as exc:
        print(f"  ⚠  PaddleOCR unavailable — skipping: {exc}")
        return None


def load_fast_plate_ocr():
    print("Loading fast-plate-ocr (cct-xs-v2-global-model)…")
    from fast_plate_ocr import LicensePlateRecognizer
    return LicensePlateRecognizer("cct-xs-v2-global-model")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare OCR backends on plate crops.")
    parser.add_argument("--crops-dir", default="runs/video_pipeline/crops", type=Path)
    parser.add_argument("--max-images", default=20, type=int, help="0 = all images")
    parser.add_argument("--output", default="runs/ocr_comparison/results.csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    crop_paths = sorted(args.crops_dir.glob("*.jpg")) + sorted(args.crops_dir.glob("*.png"))
    if not crop_paths:
        print(f"No images found in {args.crops_dir}")
        return 1
    if args.max_images:
        crop_paths = crop_paths[: args.max_images]
    print(f"Testing on {len(crop_paths)} crops from {args.crops_dir}\n")

    # --- load models ---
    easy = load_easyocr()
    paddle = load_paddle()
    fast = load_fast_plate_ocr()
    print()

    fieldnames = [
        "image",
        "easyocr_text", "easyocr_ms",
        "paddle_text",  "paddle_ms",
        "fastalpr_text","fastalpr_ms",
    ]

    rows: list[dict] = []

    for path in crop_paths:
        img = cv2.imread(str(path))
        if img is None:
            print(f"  [skip] cannot read {path.name}")
            continue

        easy_text, easy_ms = run_easyocr(img, easy)

        if paddle is not None:
            paddle_text, paddle_ms = run_paddle(img, paddle)
        else:
            paddle_text, paddle_ms = "SKIPPED", 0.0

        fast_text, fast_ms = run_fast_plate_ocr(img, fast)

        row = {
            "image":        path.name,
            "easyocr_text": easy_text,
            "easyocr_ms":   f"{easy_ms:.1f}",
            "paddle_text":  paddle_text,
            "paddle_ms":    f"{paddle_ms:.1f}",
            "fastalpr_text":fast_text,
            "fastalpr_ms":  f"{fast_ms:.1f}",
        }
        rows.append(row)

        print(
            f"{path.name}\n"
            f"  EasyOCR   : {easy_text!r:20s}  {easy_ms:6.1f} ms\n"
            f"  PaddleOCR : {paddle_text!r:20s}  {paddle_ms:6.1f} ms\n"
            f"  fast-alpr : {fast_text!r:20s}  {fast_ms:6.1f} ms\n"
        )

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # --- summary stats ---
    print(f"\nResults written to {args.output}")
    print("\nAverage latency per crop:")
    for key, label in [("easyocr_ms", "EasyOCR"), ("paddle_ms", "PaddleOCR"), ("fastalpr_ms", "fast-alpr")]:
        vals = [float(r[key]) for r in rows if r[key] != "0.0" or label != "PaddleOCR"]
        if vals:
            print(f"  {label:12s}: {sum(vals)/len(vals):.1f} ms avg")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
