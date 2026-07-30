"""影像前處理：矯正、去噪、強化線條，提升表單辨識穩定度。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_image(path: str | Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"無法讀取影像: {path}")
    return image


def save_image(path: str | Path, image: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".jpg"
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        raise ValueError(f"無法編碼影像: {path}")
    buf.tofile(str(path))


def enhance_for_ocr(image: np.ndarray) -> np.ndarray:
    """輕量強化：灰階、對比拉伸、去噪。"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
    return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)


def deskew(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5 or abs(angle) > 15:
        return image
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def preprocess(path: str | Path, output_path: str | Path | None = None) -> Path:
    image = load_image(path)
    image = deskew(image)
    image = enhance_for_ocr(image)
    out = Path(output_path) if output_path else Path(path).with_name(
        Path(path).stem + "_prep.jpg"
    )
    save_image(out, image)
    return out


def to_jpeg_bytes(path: str | Path, max_side: int = 1600) -> bytes:
    image = Image.open(path).convert("RGB")
    w, h = image.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        image = image.resize((int(w * scale), int(h * scale)))
    from io import BytesIO

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
