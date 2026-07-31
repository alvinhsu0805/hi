"""離線表頭 OCR：型號／批號／作業人員。

只用 EasyOCR（不強制依賴 paddleocr）。
Windows 以 numpy 讀圖，避免 cv2.imread 路徑問題。
"""

from __future__ import annotations

import re
import traceback
from pathlib import Path

import cv2

from .field_parsers import HeaderFields, parse_header_from_texts
from .preprocess import enhance_for_ocr, load_image, save_image


class OfflineHeaderOCR:
    def __init__(self, lang: str = "ch"):
        self.lang = lang
        self._easy = None
        self.engine_name = "not-started"
        self.last_error = ""

    def status(self) -> dict[str, str]:
        try:
            import easyocr  # noqa: F401

            easy = "installed"
        except Exception as exc:  # noqa: BLE001
            easy = f"missing:{exc}"
        return {
            "engine_name": self.engine_name,
            "easyocr": easy,
            "last_error": self.last_error,
        }

    def recognize(self, image_path: str | Path) -> tuple[HeaderFields, list[str]]:
        image_path = Path(image_path)
        texts = self._run_easyocr(image_path)
        fields = parse_header_from_texts(texts)

        # 若欄位不齊，再對表頭強化圖補一次
        if fields.warnings:
            prepared = self._prepare(image_path)
            prep_texts = self._run_easyocr(prepared)
            if prep_texts:
                merged = list(dict.fromkeys(texts + prep_texts))
                fields = parse_header_from_texts(merged)
                texts = merged

        if self.engine_name.startswith("unavailable") or self.engine_name == "not-started":
            detail = self.last_error or self.engine_name
            fields.warnings.append(
                "離線 OCR 引擎不可用。請用 py -3.12 啟動，並確認 easyocr 已安裝。"
                f" 詳細：{detail}"
            )
        elif not texts:
            fields.warnings.append("OCR 未讀到文字，請換更清楚的表頭照片。")
        return fields, texts

    def _prepare(self, image_path: Path) -> Path:
        image = load_image(image_path)
        h, w = image.shape[:2]
        header = image[0 : max(80, int(h * 0.70)), 0:w]
        header = enhance_for_ocr(header)
        header = cv2.resize(header, None, fx=1.8, fy=1.8, interpolation=cv2.INTER_CUBIC)
        out = image_path.with_name(image_path.stem + "_header_prep.jpg")
        save_image(out, header)
        return out

    def _ensure_reader(self) -> bool:
        if self._easy is not None:
            return True
        try:
            import easyocr
        except Exception as exc:  # noqa: BLE001
            self.engine_name = "unavailable:easyocr-import"
            self.last_error = str(exc)
            return False
        try:
            self._easy = easyocr.Reader(["en"], gpu=False, verbose=False)
            return True
        except Exception as exc:  # noqa: BLE001
            self.engine_name = "unavailable:easyocr-init"
            self.last_error = f"{exc}\n{traceback.format_exc()}"
            self._easy = None
            return False

    def _run_easyocr(self, image_path: Path) -> list[str]:
        if not self._ensure_reader():
            return []
        try:
            image = load_image(image_path)
            raw = self._easy.readtext(image, detail=0, paragraph=False)
        except Exception as exc:  # noqa: BLE001
            self.engine_name = "unavailable:easyocr-run"
            self.last_error = f"{exc}\n{traceback.format_exc()}"
            return []
        self.engine_name = "easyocr"
        self.last_error = ""
        return [re.sub(r"\s+", " ", str(t)).strip() for t in raw if str(t).strip()]
