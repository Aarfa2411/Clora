"""
Multimodal Engineering Drawing Schema & Data Contracts.
INDUSAI-X / SIH26117 (MRPL)
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    TAG = "TAG"
    SYMBOL = "SYMBOL"
    CONNECTIVITY = "CONNECTIVITY"
    LINE_SPEC = "LINE_SPEC"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_VISUAL_EVIDENCE = "INSUFFICIENT_VISUAL_EVIDENCE"


class BoundingBox(BaseModel):
    """
    Normalized bounding box coordinates (0.0 to 1.0).
    [ymin, xmin, ymax, xmax]
    """
    ymin: float = Field(ge=0.0, le=1.0)
    xmin: float = Field(ge=0.0, le=1.0)
    ymax: float = Field(ge=0.0, le=1.0)
    xmax: float = Field(ge=0.0, le=1.0)

    def to_list(self) -> List[float]:
        return [round(self.ymin, 4), round(self.xmin, 4), round(self.ymax, 4), round(self.xmax, 4)]

    def to_pixel_box(self, width: int, height: int) -> Dict[str, int]:
        return {
            "x": int(round(self.xmin * width)),
            "y": int(round(self.ymin * height)),
            "width": max(1, int(round((self.xmax - self.xmin) * width))),
            "height": max(1, int(round((self.ymax - self.ymin) * height))),
        }


    @classmethod
    def from_pixel_coords(
        cls, x: float, y: float, w: float, h: float, img_width: int, img_height: int
    ) -> "BoundingBox":
        if img_width <= 0 or img_height <= 0:
            return cls(ymin=0.0, xmin=0.0, ymax=1.0, xmax=1.0)
        xmin = max(0.0, min(1.0, x / img_width))
        ymin = max(0.0, min(1.0, y / img_height))
        xmax = max(0.0, min(1.0, (x + w) / img_width))
        ymax = max(0.0, min(1.0, (y + h) / img_height))
        return cls(ymin=ymin, xmin=xmin, ymax=max(ymin, ymax), xmax=max(xmin, xmax))


class VisualEvidenceItem(BaseModel):
    """Specific piece of visually grounded proof from a drawing."""
    evidence_id: str
    evidence_type: EvidenceType
    label: str
    bbox: BoundingBox
    grid_cell: str
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    numeric_score: float = 0.95
    snippet_text: str = ""
    crop_base64: Optional[str] = None


class DetectedEntity(BaseModel):
    """Engineering component or instrument detected in a drawing."""
    tag: str
    component_type: str = "valve"  # pump, valve, exchanger, instrument, vessel, line
    state: str = "UNKNOWN"  # NO, NC, FC, FO, OPERATING, STANDBY, UNKNOWN
    grid_cell: str = "Grid A1"
    tag_bbox: Optional[BoundingBox] = None
    symbol_bbox: Optional[BoundingBox] = None
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    numeric_score: float = 0.90
    raw_ocr_text: Optional[str] = None
    vlm_proposal: Optional[str] = None
    is_validated: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PipingEdge(BaseModel):
    """Topological connection between two components."""
    source_tag: str
    target_tag: str
    line_spec: Optional[str] = None
    flow_direction: str = "FORWARD"  # FORWARD, REVERSE, BIDIRECTIONAL
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    evidence_type: EvidenceType = EvidenceType.CONNECTIVITY
    is_validated: bool = False
    provenance: Dict[str, Any] = Field(default_factory=dict)


class DrawingAnalysisResult(BaseModel):
    """Comprehensive structured analysis for an engineering drawing."""
    drawing_id: str
    filename: str
    sheet_number: int = 1
    dimensions: Dict[str, int] = Field(default_factory=lambda: {"width": 1920, "height": 1080})
    grid_layout: Dict[str, Any] = Field(default_factory=dict)
    entities: List[DetectedEntity] = Field(default_factory=list)
    connectivity_edges: List[PipingEdge] = Field(default_factory=list)
    visual_evidence: List[VisualEvidenceItem] = Field(default_factory=list)
    summary: str = ""
    needs_human_review: bool = False

    def get_entity_by_tag(self, tag: str) -> Optional[DetectedEntity]:
        tag_clean = tag.strip().upper().replace(" ", "").replace("_", "-")
        for e in self.entities:
            if e.tag.strip().upper().replace(" ", "").replace("_", "-") == tag_clean:
                return e
        return None
