import cv2, sys, glob
sys.path.insert(0, ".")

from paddleocr import PaddleOCR

ocr_ar = PaddleOCR(use_angle_cls=False, lang="ar", use_gpu=False, show_log=False)
ocr_en = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=False, show_log=False)

crops = sorted(glob.glob("runs/video_pipeline/crops/*.jpg"))[:10]
print(f"Found {len(crops)} crops")
for path in crops:
    img = cv2.imread(path)
    if img is None:
        print(f"  could not read {path}")
        continue
    h = img.shape[0]
    top = img[: h // 2, :]
    bot = img[h // 2 :, :]

    r_ar = ocr_ar.ocr(top, cls=False)
    r_en = ocr_en.ocr(bot, cls=False)

    ar_texts = [f"{l[1][0]!r}({l[1][1]:.2f})" for l in (r_ar[0] or []) if l] if r_ar else []
    en_texts = [f"{l[1][0]!r}({l[1][1]:.2f})" for l in (r_en[0] or []) if l] if r_en else []
    name = path.split("\\")[-1]
    sys.stdout.write(f"{name}\n  AR: {ar_texts}\n  EN: {en_texts}\n")
    sys.stdout.flush()

print("done")


