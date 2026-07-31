"""離線表頭 OCR：型號／批號／作業人員。

優先 EasyOCR（本環境可跑、可離線）。
PaddleOCR 若可用則作為備選。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import cv2

from .field_parsers import HeaderFields, parse_header_from_texts
from .preprocess import enhance_for_ocr, load_image, save_image

# 模型下載／連線檢查可關，方便工廠離線機
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class OfflineHeaderOCR:
    def __init__(self, lang: str = "ch"):
        self.lang = lang
        self._easy = None
        self._paddle = None
        self.engine_name = "unavailable"

    def recognize(self, image_path: str | Path) -> tuple[HeaderFields, list[str]]:
        image_path = Path(image_path)
        prepared = self._prepare(image_path)
        texts = self._run_ocr(prepared)
        fields = parse_header_from_texts(texts)
        # 表頭裁切若漏字，再對原圖補跑一次合併
        if fields.warnings:
            full_texts = self._run_ocr(image_path)
            if full_texts:
                merged = list(dict.fromkeys(texts + full_texts))
                fields = parse_header_from_texts(merged)
                texts = merged
        if self.engine_name.startswith("unavailable"):
            fields.warnings.append(
                "離線 OCR 引擎不可用。請安裝 easyocr（建議）或 paddleocr，或改手動輸入。"
            )
        elif not texts:
            fields.warnings.append("OCR 未讀到文字，請換更清楚的表頭照片。")
        return fields, texts

    def _prepare(self, image_path: Path) -> Path:
        image = load_image(image_path)
        h, w = image.shape[:2]
        header = image[0 : max(80, int(h * 0.62)), 0:w]
        header = enhance_for_ocr(header)
        header = cv2.resize(header, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
        out = image_path.with_name(image_path.stem + "_header_prep.jpg")
        save_image(out, header)
        return out

    def _run_ocr(self, image_path: Path) -> list[str]:
        texts = self._run_easyocr(image_path)
        if texts:
            return texts
        return self._run_paddle(image_path)

    def _run_easyocr(self, image_path: Path) -> list[str]:
        try:
            import easyocr
        except Exception as exc:  # noqa: BLE001
            self.engine_name = f"unavailable:easyocr:{exc}"
            return []
        if self._easy is None:
            # 型號/批號/工號本身是英數；先用 en 較快且離線穩
            # 若之後要靠中文標籤定位，可改 Reader(['ch_tra','en'])
            self._easy = easyocr.Reader(["en"], gpu=False, verbose=False)
        try:
            raw = self._easy.readtext(str(image_path), detail=0, paragraph=False)
        except Exception as exc:  # noqa: BLE001
            self.engine_name = f"unavailable:easyocr-run:{exc}"
            return []
        self.engine_name = "easyocr"
        return [re.sub(r"\s+", " ", str(t)).strip() for t in raw if str(t).strip()]

    def _run_paddle(self, image_path: Path) -> list[str]:
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # noqa: BLE001
            if self.engine_name.startswith("unavailable"):
                self.engine_name = f"unavailable:paddle:{exc}"
            return []
        if self._paddle is None:
            try:
                self._paddle = PaddleOCR(
                    lang="en" if not self.lang.startswith("ch") else "ch",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except Exception as exc:  # noqa: BLE001
                self.engine_name = f"unavailable:paddle-init:{exc}"
                self._paddle = False
                return []
        if not self._paddle:
            return []
        try:
            if hasattr(self._paddle, "predict"):
                result = list(self._paddle.predict(str(image_path)))
            else:
                result = self._paddle.ocr(str(image_path))
        except Exception as exc:  # noqa: BLE001
            self.engine_name = f"unavailable:paddle-run:{exc}"
            return []
        self.engine_name = "paddleocr"
        return _flatten_paddle_result(result)


def _flatten_paddle_result(result: Any) -> list[str]:
    texts: list[str] = []
    if not result:
        return texts
    if isinstance(result, list) and result and isinstance(result[0], dict):
        for block in result:
            for item in block.get("rec_texts") or []:
                if item:
                    texts.append(str(item))
        return texts
    for page in result or []:
        if page is None:
            continue
        # paddlex result object
        if hasattr(page, "rec_texts"):
            for item in page.rec_texts or []:
                texts.append(str(item))
            continue
        if isinstance(page, dict) and "rec_texts" in page:
            for item in page.get("rec_texts") or []:
                texts.append(str(item))
            continue
        for line in page or []:
            try:
                txt = line[1][0]
            except Exception:  # noqa: BLE001
                continue
            if txt:
                texts.append(str(txt))
    return [re.sub(r"\s+", " ", t).strip() for t in texts if str(t).strip()]
