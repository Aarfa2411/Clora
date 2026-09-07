"""
Unified Evidence Schema Contract for CLORA.
Standardizes text, tables, telemetry, images, SOPs, and calculations into a single typed evidence model.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional


class EvidenceType(str, Enum):
    DOCUMENT = "DOCUMENT"
    TABLE = "TABLE"
    TELEMETRY = "TELEMETRY"
    IMAGE = "IMAGE"
    SOP = "SOP"
    EQUIPMENT_HISTORY = "EQUIPMENT_HISTORY"
    CALCULATION = "CALCULATION"
    USER_INPUT = "USER_INPUT"


@dataclass
class EvidenceLocation:
    """Granular citation location metadata."""
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    column_name: Optional[str] = None
    image_region: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Evidence:
    """
    Unified Evidence Object for Stage 2 & Stage 3 of CLORA Agent Engine.
    Separates Source Confidence (source reliability) from Verification Score (claim support).
    """
    evidence_id: str
    evidence_type: EvidenceType
    source_id: str                          # Document filename, table name, or sensor tag
    content: str                            # Extracted fact or text excerpt
    confidence: float                       # Source reliability score: Telemetry=1.0, OCR=0.82, Visual=0.78
    location: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    document_version: str = "1.0"
    status: str = "ACTIVE"
    authorized_roles: List[str] = field(default_factory=lambda: ["ENGINEER", "CHIEF_SANCTION_OFFICER", "ADMIN"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value if isinstance(self.evidence_type, EvidenceType) else self.evidence_type,
            "source_id": self.source_id,
            "content": self.content,
            "confidence": round(self.confidence, 3),
            "location": self.location,
            "timestamp": self.timestamp,
            "document_version": self.document_version,
            "status": self.status,
            "authorized_roles": self.authorized_roles,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Evidence:
        ev_type = data.get("evidence_type", EvidenceType.DOCUMENT)
        if isinstance(ev_type, str):
            try:
                ev_type = EvidenceType(ev_type.upper())
            except ValueError:
                ev_type = EvidenceType.DOCUMENT

        return cls(
            evidence_id=data.get("evidence_id", "ev_001"),
            evidence_type=ev_type,
            source_id=data.get("source_id", data.get("source_document", "doc.pdf")),
            content=data.get("content", data.get("text", "")),
            confidence=float(data.get("confidence", 0.9)),
            location=data.get("location", {"page": data.get("page_number", 1)}),
            timestamp=data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            document_version=data.get("document_version", "1.0"),
            status=data.get("status", "ACTIVE"),
            authorized_roles=data.get("authorized_roles", ["ENGINEER"]),
        )
