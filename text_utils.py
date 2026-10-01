"""
text_utils.py
Week 3 additions: text cleaning/normalization + OCR image preprocessing.
Kept separate from app.py so both app.py and train_classifier.py can reuse it.
"""

import re
from PIL import Image, ImageFilter

MIN_USEFUL_CHARS = 15  # below this we treat extracted text as "empty/too short"


# ---------------------------------------------------------------------------
# Step 2: Clean the extracted text
# ---------------------------------------------------------------------------
def clean_text(raw_text: str) -> str:
    """Normalize messy OCR/PDF text before classification & extraction.

    - collapses repeated blank lines
    - strips trailing/leading whitespace on each line
    - collapses runs of spaces/tabs
    - removes stray control characters
    """
    if not raw_text:
        return ""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    # remove non-printable/control chars except newline/tab
    text = re.sub(r"[^\x20-\x7E\n\t]", " ", text)
    # collapse spaces/tabs
    text = re.sub(r"[ \t]+", " ", text)
    # strip each line
    lines = [ln.strip() for ln in text.split("\n")]
    # drop empty lines but collapse multiple blank lines into a single blank line
    cleaned_lines = []
    prev_blank = False
    for ln in lines:
        if ln == "":
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(ln)
            prev_blank = False
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned


def is_text_too_short(text: str) -> bool:
    """True if cleaned text is empty or too short to be useful."""
    return len(text.strip()) < MIN_USEFUL_CHARS


# ---------------------------------------------------------------------------
# Step 3: Improve OCR handling — simple image preprocessing
# ---------------------------------------------------------------------------
def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Apply beginner-level preprocessing to improve OCR accuracy on
    scanned/difficult images: upscale small images, convert to grayscale,
    apply a simple threshold, and reduce noise slightly.
    """
    # Upscale small images (OCR struggles on tiny text)
    width, height = img.size
    if max(width, height) < 1000:
        scale = 1000 / max(width, height)
        img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    # Grayscale conversion
    gray = img.convert("L")

    # Mild noise reduction
    gray = gray.filter(ImageFilter.MedianFilter(size=3))

    # Simple fixed thresholding to binarize the image
    threshold = 150
    binarized = gray.point(lambda p: 255 if p > threshold else 0)

    return binarized
