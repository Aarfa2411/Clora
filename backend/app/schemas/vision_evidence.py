"""
Canonical Structured Evidence Schema and Provenance Models for Clora (INDUSAI-X).
Decouples sensitive raw artifacts from verifiable, SI-normalized structured evidence.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class DomainValidationResult(BaseModel):
    """Deterministic validation results against asset registry and physical operating envelopes."""
    equipment_match: bool = Field(default=False, description="Verified against registered asset taxonomy")
    unit_valid: bool = Field(default=False, description="Matches recognized physical dimension")
    range_valid: bool = Field(default=False, description="Within plausible physical operating bounds")
    timestamp_valid: bool = Field(default=True, description="Parses into valid ISO timestamp within operational window")
    cross_source_match: Optional[bool] = Field(default=None, description="Corroborated by telemetry or secondary logs")

    @property
    def is_fully_valid(self) -> bool:
        return self.equipment_match and self.unit_valid and self.range_valid and self.timestamp_valid


class StructuredField(BaseModel):
    """Normalized atomic field extracted from handwritten, tabular, or digital sources."""
    field_name: str
    raw_extracted_value: Union[str, float, int]
    normalized_value: Optional[float] = None  # Converted to canonical base SI unit (Pa, K, m/s, etc.)
    canonical_unit: Optional[str] = None  # Canonical SI unit (e.g. "Pa", "K", "m/s", "RPM")
    display_unit: Optional[str] = None  # Original representation (e.g. "bar", "°C", "psi")
    equipment_id: Optional[str] = None  # e.g. "P-101", "MOV-102"
    source_bbox: List[int] = Field(default_factory=list)  # [ymin, xmin, ymax, xmax] in normalized coordinates [0, 1000]
    ocr_character_quality: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    domain_validation: DomainValidationResult = Field(default_factory=DomainValidationResult)
    is_handwritten: bool = False


class ImmutableSourceArtifact(BaseModel):
    """Reference to immutable raw source file stored in secured local storage."""
    artifact_id: str
    version: int = 1
    workspace_id: str
    source_filename: str
    content_hash: str  # SHA-256 of raw source bytes
    ingestion_timestamp: str
    storage_uri: str  # Local absolute or workspace-relative path


class StructuredEvidence(BaseModel):
    """
    Canonical evidence unit. 
    Never stores sensitive raw document text directly in state/vector store,
    referencing the source_artifact_id and cryptographic content hash instead.
    """
    evidence_id: str
    source_artifact_id: str
    source_content_hash: str
    workspace_id: str
    page_number: int = 1
    extraction_method: Literal["DIGITAL_TEXT", "VLM_MULTIMODAL", "CPU_OCR", "CALCULATION_ENGINE"] = "DIGITAL_TEXT"
    verification_status: Literal["VERIFIED", "UNVERIFIED_FLAGGED", "REQUIRES_REVIEW", "INVALID"] = "VERIFIED"
    extracted_fields: List[StructuredField] = Field(default_factory=list)
    model_version: str = "local_deterministic_v1"
    preprocessing_version: str = "opencv_v1"
    timestamp: str

    def to_summary_dict(self) -> Dict[str, Any]:
        """Compact representation for agent contexts."""
        return {
            "evidence_id": self.evidence_id,
            "source_artifact_id": self.source_artifact_id,
            "page": self.page_number,
            "status": self.verification_status,
            "fields": [
                {
                    "name": f.field_name,
                    "val": f.normalized_value if f.normalized_value is not None else f.raw_extracted_value,
                    "unit": f.display_unit or f.canonical_unit,
                    "eq": f.equipment_id,
                    "valid": f.domain_validation.is_fully_valid,
                }
                for f in self.extracted_fields
            ],
        }
