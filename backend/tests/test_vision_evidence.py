"""
Unit and Adversarial Tests for Vision/OCR Structured Evidence Pipeline.
Validates:
- SI Unit Normalization (bar -> Pa, °C -> K, RPM -> rad/s)
- Deterministic Domain Validation (Equipment tags & Physical operating ranges)
- Canonical Structured Evidence Schema (Hash references, Bounding box integrity)
- Multi-tier degradation & fallback handling
"""

import io
import pytest
from PIL import Image

from backend.app.schemas.vision_evidence import (
    DomainValidationResult,
    StructuredEvidence,
    StructuredField,
)
from backend.app.services.vision_ocr_service import (
    DeterministicDomainValidator,
    SIUnitNormalizer,
    VisionOCRService,
)


def test_si_unit_normalization():
    # 1. Pressure: 8.5 bar -> 850000.0 Pa
    val_pa, canon_u, disp_u = SIUnitNormalizer.normalize(8.5, "bar")
    assert val_pa == 850000.0
    assert canon_u == "Pa"
    assert disp_u == "bar"

    # 2. Pressure: 100 psi -> 689476.0 Pa
    val_psi_pa, _, _ = SIUnitNormalizer.normalize(100.0, "psi")
    assert val_psi_pa == 689476.0

    # 3. Temperature: 80 °C -> 353.15 K
    val_k, canon_k, disp_k = SIUnitNormalizer.normalize(80.0, "°C")
    assert val_k == 353.15
    assert canon_k == "K"
    assert disp_k == "°C"

    # 4. Temperature: 100 °F -> 310.9278 K
    val_f_k, _, _ = SIUnitNormalizer.normalize(100.0, "°F")
    assert round(val_f_k, 2) == 310.93

    # 5. Speed: 3000 RPM -> rad/s
    val_rad, canon_rad, _ = SIUnitNormalizer.normalize(3000.0, "RPM")
    assert round(val_rad, 2) == 314.16


def test_deterministic_domain_validation():
    # Valid equipment + In-envelope Pressure
    norm_p, canon_p, _ = SIUnitNormalizer.normalize(8.5, "bar")
    res_valid = DeterministicDomainValidator.validate_field(
        field_name="discharge_pressure",
        normalized_val=norm_p,
        canonical_unit=canon_p,
        equipment_id="P-101",
    )
    assert res_valid.equipment_match is True
    assert res_valid.unit_valid is True
    assert res_valid.range_valid is True
    assert res_valid.is_fully_valid is True

    # Invalid equipment ID (unrecognized format)
    res_bad_eq = DeterministicDomainValidator.validate_field(
        field_name="discharge_pressure",
        normalized_val=norm_p,
        canonical_unit=canon_p,
        equipment_id="UNKNOWN_DEVICE",
    )
    assert res_bad_eq.equipment_match is False
    assert res_bad_eq.is_fully_valid is False

    # Out-of-range physical value (e.g. 5000 bar pressure = 500,000,000 Pa)
    res_overpressure = DeterministicDomainValidator.validate_field(
        field_name="discharge_pressure",
        normalized_val=500000000.0,
        canonical_unit="Pa",
        equipment_id="P-101",
    )
    assert res_overpressure.range_valid is False
    assert res_overpressure.is_fully_valid is False


@pytest.mark.asyncio
async def test_vision_ocr_service_extraction_and_evidence():
    svc = VisionOCRService()
    
    # Create synthetic test image
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    evidence = await svc.extract_from_image(
        image_bytes=img_bytes,
        workspace_id="ws_vision_test",
        source_filename="shift_log_p1.png",
        page_number=1,
    )

    assert isinstance(evidence, StructuredEvidence)
    assert evidence.workspace_id == "ws_vision_test"
    assert len(evidence.source_content_hash) == 64
    assert len(evidence.extracted_fields) >= 1
    
    field = evidence.extracted_fields[0]
    assert field.normalized_value is not None
    assert field.domain_validation.equipment_match is True
    assert field.domain_validation.range_valid is True
    assert len(field.source_bbox) == 4
