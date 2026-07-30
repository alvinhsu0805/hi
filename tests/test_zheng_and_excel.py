from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.excel_writer import ExcelWriter
from app.ocr_engine import FormOCREngine
from app.schema import load_schema
from app.zheng_count import count_zheng_marks, strokes_to_zheng_display


class ZhengCountTests(unittest.TestCase):
    def test_full_zheng(self):
        self.assertEqual(count_zheng_marks("正")[0], 5)
        self.assertEqual(count_zheng_marks("正正一")[0], 11)

    def test_display(self):
        self.assertEqual(strokes_to_zheng_display(6), "正一")


class AmtSchemaTests(unittest.TestCase):
    def test_schema_has_amt_codes(self):
        schema = load_schema()
        self.assertEqual(schema.form_id, "QWF-ME061")
        keys = {d.key for d in schema.defect_items}
        self.assertIn("P03", keys)
        self.assertIn("PB01", keys)
        self.assertIn("GB01", keys)
        self.assertIn("FA01", keys)
        self.assertGreaterEqual(len(schema.defect_items), 50)


class AmtPipelineTests(unittest.TestCase):
    def test_sample_demo_and_excel(self):
        schema = load_schema()
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "amt_qwf_me061_sample.jpg"
            cv2.imwrite(str(img), np.full((400, 600, 3), 240, np.uint8))

            engine = FormOCREngine(schema)
            result = engine.recognize(img)
            self.assertEqual(result.model_no, "10819-B")
            self.assertEqual(result.lot_no, "26-06-209")
            self.assertEqual(result.total_qty, 142)
            self.assertEqual(result.total_defects_reported, 15)
            self.assertGreaterEqual(result.total_defects, 15)

            xlsx = Path(tmp) / "out.xlsx"
            writer = ExcelWriter(schema, xlsx)
            row = writer.append_result(result, reviewed=True)
            self.assertGreaterEqual(row, 2)
            self.assertTrue(xlsx.exists())


if __name__ == "__main__":
    unittest.main()
