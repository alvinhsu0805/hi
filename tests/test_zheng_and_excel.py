from __future__ import annotations

import unittest

from app.zheng_count import count_zheng_marks, strokes_to_zheng_display


class ZhengCountTests(unittest.TestCase):
    def test_full_zheng(self):
        self.assertEqual(count_zheng_marks("正")[0], 5)
        self.assertEqual(count_zheng_marks("正正")[0], 10)
        self.assertEqual(count_zheng_marks("正正一")[0], 11)

    def test_partial_strokes(self):
        self.assertEqual(count_zheng_marks("一")[0], 1)
        self.assertEqual(count_zheng_marks("丁")[0], 2)
        self.assertEqual(count_zheng_marks("下")[0], 3)
        self.assertEqual(count_zheng_marks("止")[0], 4)

    def test_empty_and_digits(self):
        self.assertEqual(count_zheng_marks("")[0], 0)
        self.assertEqual(count_zheng_marks("無")[0], 0)
        self.assertEqual(count_zheng_marks("12")[0], 12)

    def test_display(self):
        self.assertEqual(strokes_to_zheng_display(0), "")
        self.assertEqual(strokes_to_zheng_display(5), "正")
        self.assertEqual(strokes_to_zheng_display(6), "正一")
        self.assertEqual(strokes_to_zheng_display(11), "正正一")


class ExcelPipelineTests(unittest.TestCase):
    def test_append_demo_result(self):
        from pathlib import Path
        import tempfile

        from app.excel_writer import ExcelWriter
        from app.ocr_engine import FormOCREngine
        from app.schema import load_schema

        schema = load_schema()
        with tempfile.TemporaryDirectory() as tmp:
            # 用檔名示範模式
            img = Path(tmp) / "20260730_WO001_PN100_王小明.jpg"
            # 建立最小可讀影像
            import numpy as np
            import cv2

            blank = np.full((200, 300, 3), 255, dtype=np.uint8)
            cv2.imwrite(str(img), blank)

            engine = FormOCREngine(schema)
            result = engine.recognize(img)
            self.assertEqual(result.work_order, "WO001")
            self.assertEqual(result.product_no, "PN100")
            self.assertEqual(result.operator, "王小明")

            xlsx = Path(tmp) / "out.xlsx"
            writer = ExcelWriter(schema, xlsx)
            row = writer.append_result(result, reviewed=False)
            self.assertGreaterEqual(row, 2)
            self.assertTrue(xlsx.exists())


if __name__ == "__main__":
    unittest.main()
