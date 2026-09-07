"""
Unit & Integration Tests for Industrial OCR & Preprocessing Pipeline.
INDUSAI-X / SIH Problem Statement 26117 (MRPL)
"""

import os
import unittest
from PIL import Image, ImageDraw

from data_intelligence.ocr_pipeline import (
    PlantEntityValidator,
    ImagePreprocessor,
    SpatialTableReconstructor,
    OCRQualityAssessor,
    TesseractOCREngine
)


class TestOCRPipeline(unittest.TestCase):

    def setUp(self):
        self.ocr_engine = TesseractOCREngine()

    def test_plant_entity_validator_approved_tags(self):
        sample_text = "Inspection of Boiler Feedwater Pump P-102A and secondary pump P-102B completed."
        res = PlantEntityValidator.validate_equipment_tags(sample_text)
        self.assertIn("P-102A", res["valid_tags"])
        self.assertIn("P-102B", res["valid_tags"])
        self.assertFalse(res["has_warnings"])
        self.assertEqual(len(res["suspicious_tags"]), 0)

    def test_plant_entity_validator_ocr_corruption_warning(self):
        # P-1028 is a common OCR digit misrecognition of P-102B
        corrupted_text = "Vibration alert on asset P-1028 in crude unit CDU-1."
        res = PlantEntityValidator.validate_equipment_tags(corrupted_text)
        self.assertIn("CDU-1", res["valid_tags"])
        self.assertIn("P-1028", res["suspicious_tags"])
        self.assertTrue(res["has_warnings"])
        self.assertTrue(any("likely OCR misrecognition of approved asset" in w for w in res["warnings"]))

    def test_plant_entity_validator_custom_registry(self):
        custom_registry = {"TURBINE-01", "GEN-99"}
        text = "Check TURBINE-01 and TURBINE-02 status."
        res = PlantEntityValidator.validate_equipment_tags(text, known_registry=custom_registry)
        self.assertIn("TURBINE-01", res["valid_tags"])
        self.assertIn("TURBINE-02", res["suspicious_tags"])
        self.assertTrue(res["has_warnings"])

    def test_image_preprocessing_and_deskew(self):
        # Create a test synthetic image with text lines
        img = Image.new("RGB", (400, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "MANGALORE REFINERY & PETROCHEMICALS LIMITED", fill=(0, 0, 0))
        draw.text((20, 60), "EQUIPMENT INSPECTION REPORT: P-102A", fill=(0, 0, 0))
        draw.text((20, 90), "VIBRATION RMS: 7.8 mm/s - CRITICAL ACTION", fill=(0, 0, 0))

        # Rotate slightly by 4 degrees
        skewed = img.rotate(4, expand=True, fillcolor=(255, 255, 255))

        # Test preprocessor
        enhanced, angle = ImagePreprocessor.deskew_and_enhance(
            skewed,
            auto_deskew=True,
            enhance_contrast=True,
            denoise=True
        )

        self.assertIsNotNone(enhanced)
        self.assertIsInstance(angle, float)
        self.assertEqual(enhanced.mode, "RGB")

    def test_spatial_table_reconstruction(self):
        mock_ocr_data = {
            "text": ["Tag", "Parameter", "Observed", "Threshold", "Severity",
                     "P-102A", "Vibration", "7.8 mm/s", "4.5 mm/s", "CRITICAL",
                     "P-102B", "Vibration", "2.1 mm/s", "4.5 mm/s", "NORMAL"],
            "conf": [95, 92, 94, 91, 96,
                     94, 93, 89, 90, 95,
                     92, 91, 93, 88, 94],
            "left": [50, 150, 260, 370, 480,
                     50, 150, 260, 370, 480,
                     50, 150, 260, 370, 480],
            "top": [100, 102, 99, 101, 100,
                    130, 131, 129, 132, 130,
                    160, 159, 161, 160, 162],
            "width": [40, 80, 60, 60, 50,
                      40, 80, 60, 60, 60,
                      40, 80, 60, 60, 50],
            "height": [15, 15, 15, 15, 15,
                       15, 15, 15, 15, 15,
                       15, 15, 15, 15, 15]
        }

        tables = SpatialTableReconstructor.reconstruct_table(mock_ocr_data, y_tolerance=8.0)
        self.assertEqual(len(tables), 3)
        self.assertEqual(tables[0], ["Tag", "Parameter", "Observed", "Threshold", "Severity"])
        self.assertEqual(tables[1], ["P-102A", "Vibration", "7.8 mm/s", "4.5 mm/s", "CRITICAL"])
        self.assertEqual(tables[2], ["P-102B", "Vibration", "2.1 mm/s", "4.5 mm/s", "NORMAL"])

    def test_key_value_pair_extraction(self):
        sample_text = """
        Report No: MRPL/INSP/2026/CDU-042
        Plant Unit: Crude Distillation Unit-1 (CDU-1)
        Lead Inspector: R. K. Sharma
        Status: ACTION REQUIRED - SEVERE
        """
        kv = SpatialTableReconstructor.extract_key_value_pairs(sample_text)
        self.assertEqual(kv.get("Report No"), "MRPL/INSP/2026/CDU-042")
        self.assertEqual(kv.get("Plant Unit"), "Crude Distillation Unit-1 (CDU-1)")
        self.assertEqual(kv.get("Lead Inspector"), "R. K. Sharma")
        self.assertEqual(kv.get("Status"), "ACTION REQUIRED - SEVERE")

    def test_ocr_quality_assessor_high_confidence(self):
        mock_ocr_data = {
            "text": ["P-102A", "Bearing", "Inspection", "Passed"],
            "conf": [95, 92, 94, 91],
            "left": [10, 50, 100, 150],
            "top": [10, 10, 10, 10],
            "width": [30, 40, 40, 30],
            "height": [12, 12, 12, 12]
        }
        mean_conf, word_boxes, needs_review, reason, tier = OCRQualityAssessor.compute_metrics(mock_ocr_data)
        self.assertGreaterEqual(mean_conf, 90.0)
        self.assertFalse(needs_review)
        self.assertEqual(len(word_boxes), 4)
        self.assertEqual(tier, "TIER_1_HIGH_CONFIDENCE")

    def test_ocr_quality_assessor_low_confidence_flagged(self):
        mock_ocr_data = {
            "text": ["P?102~", "B#ar!ng", "Insp??tion", "Fa;led"],
            "conf": [45, 38, 52, 40],
            "left": [10, 50, 100, 150],
            "top": [10, 10, 10, 10],
            "width": [30, 40, 40, 30],
            "height": [12, 12, 12, 12]
        }
        mean_conf, word_boxes, needs_review, reason, tier = OCRQualityAssessor.compute_metrics(mock_ocr_data)
        self.assertLess(mean_conf, 60.0)
        self.assertTrue(needs_review)
        self.assertIn("Critical low OCR confidence", reason)
        self.assertEqual(tier, "TIER_4_MANDATORY_REVIEW")


if __name__ == "__main__":
    unittest.main()
