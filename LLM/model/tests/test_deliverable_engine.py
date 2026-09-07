"""
Unit tests for Evidence Manifest Generator and Deliverable Engine.
"""

import os
import json
import pytest
from data_intelligence.deliverable_engine import DeliverableEngine


def test_deliverable_engine_all_outputs(tmp_path):
    output_dir = str(tmp_path / "test_deliverables")
    engine = DeliverableEngine()

    dummy_state = {
        "trace_id": "TRC-TEST-999",
        "user_query": "Test query for deliverable generation",
        "verification_score": 0.95,
        "verification_status": "SUPPORTED",
        "claims": [{"text": "Pump P-101 vibration was 8.42 mm/s", "status": "SUPPORTED"}],
        "evidence": [
            {
                "evidence_id": "EV-001",
                "source_id": "pump.csv",
                "evidence_type": "TELEMETRY",
                "content": "Peak vibration 8.42 mm/s BREACHED",
                "confidence": 1.0,
            }
        ],
    }

    res = engine.generate_package(dummy_state, output_dir=output_dir, format_type="all")
    assert res["status"] == "SUCCESS"
    assert "docx" in res["generated_files"]
    assert "xlsx" in res["generated_files"]
    assert "pptx" in res["generated_files"]
    assert "zip_package" in res["generated_files"]

    assert os.path.exists(res["generated_files"]["evidence_manifest"])
    with open(res["generated_files"]["evidence_manifest"], "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    assert manifest_data["trace_id"] == "TRC-TEST-999"
    assert manifest_data["verification"]["verification_score"] == 0.95
