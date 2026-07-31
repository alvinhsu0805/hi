from __future__ import annotations

import unittest

from app.field_parsers import (
    normalize_lot,
    normalize_model,
    normalize_operators,
    parse_header_from_texts,
)


class FieldParserTests(unittest.TestCase):
    def test_lot_normalization(self):
        pretty, normalized = normalize_lot("26-07-341")
        self.assertEqual(pretty, "26-07-341")
        self.assertEqual(normalized, "20260700341")

        pretty, normalized = normalize_lot("26/7/12")
        self.assertEqual(normalized, "20260700012")

        pretty, normalized = normalize_lot("26-07_341")
        self.assertEqual(normalized, "20260700341")

    def test_model(self):
        self.assertEqual(normalize_model("91-28190-00C"), "91-28190-00C")
        self.assertEqual(normalize_model("型號：91-28190-00c"), "91-28190-00C")
        self.assertEqual(normalize_model("10819-B"), "")
        # OCR 把 00C 讀成 0OC
        self.assertEqual(normalize_model("91-28190-0OC"), "91-28190-00C")

    def test_operator_five_digits(self):
        self.assertEqual(normalize_operators("10672"), ["10672"])
        self.assertEqual(normalize_operators("12449 / 12129"), ["12449", "12129"])
        self.assertEqual(normalize_operators("10672-10"), ["10672"])

    def test_parse_header_texts(self):
        fields = parse_header_from_texts(
            [
                "外觀檢驗暨首件檢查表",
                "型號 91-28190-00C",
                "批號 26-07-341",
                "作業人員 10672",
            ]
        )
        self.assertEqual(fields.model_no, "91-28190-00C")
        self.assertEqual(fields.lot_normalized, "20260700341")
        self.assertEqual(fields.operator, "10672")
        self.assertEqual(fields.warnings, [])

    def test_operator_not_from_model_middle(self):
        fields = parse_header_from_texts(
            ["Model 91-28190-00C", "Lot 26-07-341", "Operator 10672"]
        )
        self.assertEqual(fields.model_no, "91-28190-00C")
        self.assertEqual(fields.operator, "10672")
        self.assertNotIn("28190", fields.operators)


if __name__ == "__main__":
    unittest.main()
