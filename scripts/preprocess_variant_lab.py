<<<<<<< HEAD
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.image_utils import preprocess_plate_crop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate visual preprocessing variants for plate crops (no OCR)."
    )
    parser.add_argument("--input-dir", required=True, type=Path, help="Folder with plate crops.")
    parser.add_argument(
        "--output-dir",
        default=Path("runs/preprocess_variant_lab"),
        type=Path,
        help="Where variant images and contact sheets are written.",
    )
    parser.add_argument("--limit", default=0, type=int, help="0 means process all images.")
    parser.add_argument(
        "--include-preprocessed",
        action="store_true",
        help="Include files that already look preprocessed (e.g. *_preprocessed.jpg).",
    )
    parser.add_argument(
        "--sheet-thumb-height",
        default=180,
        type=int,
        help="Thumbnail height used in contact sheets.",
    )
    return parser.parse_args()


def _list_images(input_dir: Path, include_preprocessed: bool) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in exts)
    if include_preprocessed:
        return images
    return [path for path in images if "_preprocessed" not in path.stem]


def _to_bgr(image: Any) -> Any:
    import cv2

    if image is None:
        return image
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _build_variants(image: Any) -> dict[str, Any]:
    import cv2

    variants: dict[str, Any] = {}
    variants["original"] = image
    variants["current_pipeline"] = preprocess_plate_crop(image)

    up2 = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    up3 = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    variants["up2"] = up2
    variants["up3"] = up3

    for prefix, source in (("up2", up2), ("up3", up3)):
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(12, 12)).apply(gray)
        variants[f"{prefix}_clahe"] = clahe

        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        sharp = cv2.addWeighted(clahe, 1.45, blur, -0.45, 0)
        variants[f"{prefix}_sharp"] = sharp

        bilateral = cv2.bilateralFilter(gray, d=7, sigmaColor=40, sigmaSpace=40)
        variants[f"{prefix}_bilateral"] = bilateral

        denoise = cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)
        variants[f"{prefix}_denoise"] = denoise

        adaptive = cv2.adaptiveThreshold(
            sharp,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
        variants[f"{prefix}_adaptive"] = adaptive

        _, otsu = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants[f"{prefix}_otsu"] = otsu

    return variants


def _contact_sheet(variants: dict[str, Any], thumb_h: int = 180) -> Any:
    import cv2
    import numpy as np

    thumbs: list[Any] = []

    for name, image in variants.items():
        bgr = _to_bgr(image)
        h, w = bgr.shape[:2]
        scale = thumb_h / max(1, h)
        tw = max(1, int(w * scale))
        thumb = cv2.resize(bgr, (tw, thumb_h), interpolation=cv2.INTER_AREA)

        label_h = 26
        canvas = np.full((thumb_h + label_h, tw, 3), 24, dtype=np.uint8)
        canvas[:thumb_h, :tw] = thumb
        cv2.putText(
            canvas,
            name,
            (6, thumb_h + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (230, 230, 230),
            1,
            cv2.LINE_AA,
        )
        thumbs.append(canvas)

    if not thumbs:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    gap = 8
    total_w = sum(img.shape[1] for img in thumbs) + gap * (len(thumbs) - 1)
    total_h = max(img.shape[0] for img in thumbs)
    sheet = np.full((total_h, total_w, 3), 16, dtype=np.uint8)

    x = 0
    for img in thumbs:
        h, w = img.shape[:2]
        sheet[:h, x : x + w] = img
        x += w + gap

    return sheet


def main() -> int:
    import cv2

    args = parse_args()

    if not args.input_dir.exists():
        raise FileNotFoundError(f"input directory not found: {args.input_dir}")

    images = _list_images(args.input_dir, include_preprocessed=args.include_preprocessed)
    if args.limit:
        images = images[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = args.output_dir / "variants"
    sheets_dir = args.output_dir / "sheets"
    variants_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.output_dir / "variant_manifest.csv"

    processed = 0
    variant_count = 0

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["input_image", "variant", "variant_path", "sheet_path"],
        )
        writer.writeheader()

        for image_path in images:
            image = cv2.imread(str(image_path))
            if image is None:
                continue

            variants = _build_variants(image)

            sheet_path = sheets_dir / f"{image_path.stem}_sheet.jpg"
            sheet = _contact_sheet(variants, thumb_h=args.sheet_thumb_height)
            cv2.imwrite(str(sheet_path), sheet)

            for name, variant in variants.items():
                out_path = variants_dir / f"{image_path.stem}_{name}.jpg"
                cv2.imwrite(str(out_path), _to_bgr(variant))
                writer.writerow(
                    {
                        "input_image": str(image_path),
                        "variant": name,
                        "variant_path": str(out_path),
                        "sheet_path": str(sheet_path),
                    }
                )
                variant_count += 1

            processed += 1
            print(f"[{processed}/{len(images)}] {image_path.name}: {len(variants)} variants")

    print(
        f"Done. Inputs: {processed}, variants: {variant_count}.\n"
        f"Manifest: {csv_path}\n"
        f"Sheets: {sheets_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
=======
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.image_utils import preprocess_plate_crop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate visual preprocessing variants for plate crops (no OCR)."
    )
    parser.add_argument("--input-dir", required=True, type=Path, help="Folder with plate crops.")
    parser.add_argument(
        "--output-dir",
        default=Path("runs/preprocess_variant_lab"),
        type=Path,
        help="Where variant images and contact sheets are written.",
    )
    parser.add_argument("--limit", default=0, type=int, help="0 means process all images.")
    parser.add_argument(
        "--include-preprocessed",
        action="store_true",
        help="Include files that already look preprocessed (e.g. *_preprocessed.jpg).",
    )
    parser.add_argument(
        "--sheet-thumb-height",
        default=180,
        type=int,
        help="Thumbnail height used in contact sheets.",
    )
    return parser.parse_args()


def _list_images(input_dir: Path, include_preprocessed: bool) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in exts)
    if include_preprocessed:
        return images
    return [path for path in images if "_preprocessed" not in path.stem]


def _to_bgr(image: Any) -> Any:
    import cv2

    if image is None:
        return image
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _build_variants(image: Any) -> dict[str, Any]:
    import cv2

    variants: dict[str, Any] = {}
    variants["original"] = image
    variants["current_pipeline"] = preprocess_plate_crop(image)

    up2 = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    up3 = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    variants["up2"] = up2
    variants["up3"] = up3

    for prefix, source in (("up2", up2), ("up3", up3)):
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(12, 12)).apply(gray)
        variants[f"{prefix}_clahe"] = clahe

        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        sharp = cv2.addWeighted(clahe, 1.45, blur, -0.45, 0)
        variants[f"{prefix}_sharp"] = sharp

        bilateral = cv2.bilateralFilter(gray, d=7, sigmaColor=40, sigmaSpace=40)
        variants[f"{prefix}_bilateral"] = bilateral

        denoise = cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)
        variants[f"{prefix}_denoise"] = denoise

        adaptive = cv2.adaptiveThreshold(
            sharp,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
        variants[f"{prefix}_adaptive"] = adaptive

        _, otsu = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants[f"{prefix}_otsu"] = otsu

    return variants


def _contact_sheet(variants: dict[str, Any], thumb_h: int = 180) -> Any:
    import cv2
    import numpy as np

    thumbs: list[Any] = []

    for name, image in variants.items():
        bgr = _to_bgr(image)
        h, w = bgr.shape[:2]
        scale = thumb_h / max(1, h)
        tw = max(1, int(w * scale))
        thumb = cv2.resize(bgr, (tw, thumb_h), interpolation=cv2.INTER_AREA)

        label_h = 26
        canvas = np.full((thumb_h + label_h, tw, 3), 24, dtype=np.uint8)
        canvas[:thumb_h, :tw] = thumb
        cv2.putText(
            canvas,
            name,
            (6, thumb_h + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (230, 230, 230),
            1,
            cv2.LINE_AA,
        )
        thumbs.append(canvas)

    if not thumbs:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    gap = 8
    total_w = sum(img.shape[1] for img in thumbs) + gap * (len(thumbs) - 1)
    total_h = max(img.shape[0] for img in thumbs)
    sheet = np.full((total_h, total_w, 3), 16, dtype=np.uint8)

    x = 0
    for img in thumbs:
        h, w = img.shape[:2]
        sheet[:h, x : x + w] = img
        x += w + gap

    return sheet


def main() -> int:
    import cv2

    args = parse_args()

    if not args.input_dir.exists():
        raise FileNotFoundError(f"input directory not found: {args.input_dir}")

    images = _list_images(args.input_dir, include_preprocessed=args.include_preprocessed)
    if args.limit:
        images = images[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = args.output_dir / "variants"
    sheets_dir = args.output_dir / "sheets"
    variants_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.output_dir / "variant_manifest.csv"

    processed = 0
    variant_count = 0

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["input_image", "variant", "variant_path", "sheet_path"],
        )
        writer.writeheader()

        for image_path in images:
            image = cv2.imread(str(image_path))
            if image is None:
                continue

            variants = _build_variants(image)

            sheet_path = sheets_dir / f"{image_path.stem}_sheet.jpg"
            sheet = _contact_sheet(variants, thumb_h=args.sheet_thumb_height)
            cv2.imwrite(str(sheet_path), sheet)

            for name, variant in variants.items():
                out_path = variants_dir / f"{image_path.stem}_{name}.jpg"
                cv2.imwrite(str(out_path), _to_bgr(variant))
                writer.writerow(
                    {
                        "input_image": str(image_path),
                        "variant": name,
                        "variant_path": str(out_path),
                        "sheet_path": str(sheet_path),
                    }
                )
                variant_count += 1

            processed += 1
            print(f"[{processed}/{len(images)}] {image_path.name}: {len(variants)} variants")

    print(
        f"Done. Inputs: {processed}, variants: {variant_count}.\n"
        f"Manifest: {csv_path}\n"
        f"Sheets: {sheets_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
>>>>>>> 0b51e9811058d73267f663c69338d377595aea4a
