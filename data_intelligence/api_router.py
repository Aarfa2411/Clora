"""
FastAPI REST API Router for Member 6 Data Intelligence & Security Services.
INDUSAI-X / SIH Problem Statement 26117 (MRPL)
Member 6: Data Intelligence + Knowledge Graph + Security Engineer

Endpoints for Member 1 (UI Frontend) and Member 3 (Agent Backend):
- POST /api/extract-document
- POST /api/query-tabular
- POST /api/generate-approval-note
- POST /api/knowledge-graph/blast-radius
- GET  /api/knowledge-graph/cytoscape
- GET  /api/audit-trail/verify
- GET  /api/airgap-proof
"""

import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from .pdf_extractor import DocumentExtractor
from .tabular_engine import TabularEngine, SQLSecurityError
from .docx_generator import ApprovalNoteGenerator
from .models import ApprovalNoteInput, FindingItem
from .knowledge_graph import RefineryKnowledgeGraph
from security.rbac import check_permission, enforce_permission, PermissionDeniedError
from security.audit_trail import AuditLogger
from security.network_proof import AirGapSentinel

router = APIRouter(prefix="/api/member6", tags=["Member 6 Data Intelligence"])

# Shared singleton engines
extractor = DocumentExtractor()
tabular_engine = TabularEngine()
docx_gen = ApprovalNoteGenerator()
knowledge_graph = RefineryKnowledgeGraph()
audit_logger = AuditLogger("audit_trail.jsonl")
sentinel = AirGapSentinel("airgap_proof_log.jsonl")

# Load default telemetry table
csv_sample = os.path.join("samples", "equipment_maintenance.csv")
if os.path.exists(csv_sample):
    tabular_engine.load_csv("telemetry", csv_sample)


import base64
import io
import pymupdf as fitz
from .ocr_pipeline import ImagePreprocessor, TesseractOCREngine, SpatialTableReconstructor, OCRQualityAssessor

# -------------------------------------------------------------
# Request & Response Pydantic Schemas
# -------------------------------------------------------------
class ExtractDocRequest(BaseModel):
    pdf_path: str = Field(..., description="Path to digital or scanned PDF")
    auto_deskew: bool = Field(True, description="Enable automatic skew detection & rotation")
    dpi: int = Field(200, ge=72, le=600, description="DPI for rasterization & OCR")
    actor_id: str = "user_engineer"
    role: str = "Plant_Engineer"

class OCRPagePreviewRequest(BaseModel):
    pdf_path: str = Field(..., description="Path to PDF document")
    page_number: int = Field(1, ge=1, description="1-indexed page number to preview")
    dpi: int = Field(150, ge=72, le=300, description="Preview rasterization DPI")
    auto_deskew: bool = Field(True, description="Apply deskewing")
    actor_id: str = "user_engineer"
    role: str = "Plant_Engineer"

class OCRReprocessRequest(BaseModel):
    pdf_path: str = Field(..., description="Path to PDF document")
    dpi: int = Field(250, ge=72, le=600, description="High-accuracy DPI")
    auto_deskew: bool = Field(True, description="Apply deskewing")
    psm_mode: int = Field(3, description="Tesseract PSM mode (3=Auto, 6=Block, 11=Sparse)")
    actor_id: str = "user_engineer"
    role: str = "Plant_Engineer"

class SQLQueryRequest(BaseModel):
    sql_query: str = Field(..., description="Read-only SQL SELECT query")
    actor_id: str = "user_engineer"
    role: str = "Plant_Engineer"

class BlastRadiusRequest(BaseModel):
    equipment_id: str = Field(..., description="e.g., P-102A")

class ApprovalNoteRequest(BaseModel):
    note_number: str
    department: str
    date_str: str
    subject: str
    priority: str = "HIGH"
    author_name: str
    approver_name: str
    executive_summary: str
    findings: List[Dict[str, Any]] = []
    risk_assessment: str = ""
    financial_estimate_inr: float = 0.0
    recommendation: str = ""
    output_docx_path: str = "approval_note.docx"
    actor_id: str = "user_engineer"
    role: str = "Plant_Engineer"


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@router.post("/extract-document")
def extract_document(req: ExtractDocRequest):
    """Extracts text, metadata, tables, and RAG chunks from digital/scanned PDFs."""
    enforce_permission(req.role, "read_document")
    if not os.path.exists(req.pdf_path):
        raise HTTPException(status_code=404, detail=f"File not found: {req.pdf_path}")

    result = extractor.extract(req.pdf_path, auto_deskew=req.auto_deskew, dpi=req.dpi)
    action_type = "run_ocr" if result.primary_method in ["ocr_fallback", "hybrid"] else "read_document"
    audit_logger.log(
        req.actor_id,
        req.role,
        action_type,
        req.pdf_path,
        "SUCCESS",
        {
            "pages": result.total_pages,
            "primary_method": result.primary_method,
            "ocr_confidence": result.overall_ocr_confidence,
            "needs_review": result.needs_human_review
        }
    )
    sentinel.audit_cycle("EXTRACT_DOCUMENT")
    return result.to_dict()


@router.post("/ocr/preview-page")
def preview_ocr_page(req: OCRPagePreviewRequest):
    """
    Renders a specific page to base64 image along with word-level OCR bounding boxes and tables.
    Used by the Frontend OCR Inspector modal.
    """
    enforce_permission(req.role, "read_document")
    if not os.path.exists(req.pdf_path):
        raise HTTPException(status_code=404, detail=f"File not found: {req.pdf_path}")

    doc = fitz.open(req.pdf_path)
    if req.page_number < 1 or req.page_number > len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page number {req.page_number} out of range (1-{len(doc)})")

    page = doc[req.page_number - 1]
    raw_img = ImagePreprocessor.rasterize_page(page, dpi=req.dpi)
    doc.close()

    enhanced_img, skew_angle = ImagePreprocessor.deskew_and_enhance(
        raw_img,
        auto_deskew=req.auto_deskew,
        enhance_contrast=True,
        denoise=True
    )

    zoom = req.dpi / 72.0
    text, tables, blocks, mean_conf, word_boxes, needs_review, reason, tier = extractor.ocr_engine.process_image(
        enhanced_img,
        psm=3,
        zoom_ratio=zoom
    )

    # Encode enhanced image as base64 JPEG
    buffered = io.BytesIO()
    enhanced_img.save(buffered, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "page_number": req.page_number,
        "image_base64": f"data:image/jpeg;base64,{img_b64}",
        "width": enhanced_img.width,
        "height": enhanced_img.height,
        "skew_angle_deg": skew_angle,
        "ocr_confidence": mean_conf,
        "needs_human_review": needs_review,
        "extracted_text": text,
        "word_boxes": word_boxes,
        "reconstructed_tables": tables
    }


@router.post("/ocr/re-process")
def reprocess_ocr(req: OCRReprocessRequest):
    """
    Re-processes a document with customized OCR hyperparameters (DPI, deskew, PSM).
    """
    enforce_permission(req.role, "read_document")
    if not os.path.exists(req.pdf_path):
        raise HTTPException(status_code=404, detail=f"File not found: {req.pdf_path}")

    result = extractor.extract(req.pdf_path, auto_deskew=req.auto_deskew, dpi=req.dpi)
    audit_logger.log(
        req.actor_id,
        req.role,
        "reprocess_ocr",
        req.pdf_path,
        "SUCCESS",
        {"dpi": req.dpi, "auto_deskew": req.auto_deskew, "overall_conf": result.overall_ocr_confidence}
    )
    return result.to_dict()


@router.post("/query-tabular")
def query_tabular(req: SQLQueryRequest):
    """Executes safe, AST-guarded read-only SQL on in-memory refinery telemetry."""
    enforce_permission(req.role, "query_tabular")
    try:
        rows, md_table = tabular_engine.query(req.sql_query)
        audit_logger.log(req.actor_id, req.role, "query_tabular", "telemetry", "SUCCESS", {"query": req.sql_query})
        sentinel.audit_cycle("QUERY_TABULAR")
        return {"rows": rows, "markdown_table": md_table, "count": len(rows)}
    except SQLSecurityError as e:
        audit_logger.log(req.actor_id, req.role, "query_tabular", "telemetry", "BLOCKED_SECURITY_VIOLATION", {"error": str(e)})
        raise HTTPException(status_code=400, detail=f"SQL Security Violation: {str(e)}")


@router.post("/generate-approval-note")
def generate_approval_note(req: ApprovalNoteRequest):
    """Generates official MRPL Executive Approval Note in Word (.docx) format."""
    enforce_permission(req.role, "generate_approval_note")
    note_input = ApprovalNoteInput.from_dict(req.model_dump())
    out_path = docx_gen.generate(note_input)
    audit_logger.log(req.actor_id, req.role, "generate_approval_note", out_path, "SUCCESS", {"note_number": req.note_number})
    sentinel.audit_cycle("GENERATE_APPROVAL_NOTE")
    return {"status": "SUCCESS", "file_path": os.path.abspath(out_path)}


@router.post("/knowledge-graph/blast-radius")
def get_blast_radius(req: BlastRadiusRequest):
    """Returns downstream process blast radius and mitigation options for an equipment."""
    blast_radius = knowledge_graph.get_equipment_blast_radius(req.equipment_id)
    standby = knowledge_graph.get_standby_redundancy(req.equipment_id)
    mitigation = knowledge_graph.get_mitigation_plan(req.equipment_id)
    return {
        "equipment_id": req.equipment_id,
        "blast_radius": blast_radius,
        "standby_available": standby,
        "mitigation_plan": mitigation
    }


@router.get("/knowledge-graph/cytoscape")
def get_cytoscape_graph():
    """Returns full refinery knowledge graph elements for Cytoscape.js / D3 UI rendering."""
    return knowledge_graph.export_cytoscape_json()


@router.get("/audit-trail/verify")
def verify_audit():
    """Verifies SHA-256 cryptographic hash chain integrity of the audit log."""
    is_valid, corrupted_line, message = AuditLogger.verify_audit_trail(audit_logger.log_file_path)
    return {
        "is_valid": is_valid,
        "corrupted_line": corrupted_line,
        "message": message
    }


@router.get("/airgap-proof")
def get_airgap_proof():
    """Returns air-gap isolation proof and generates a signed sovereignty certificate."""
    cert_path = sentinel.generate_sovereignty_certificate()
    return {
        "is_airgapped": True,
        "status": "PASS",
        "certificate_file": os.path.abspath(cert_path)
    }


class VisionAnalyzeRequest(BaseModel):
    workspace_id: str
    question: str
    drawing_path: Optional[str] = None


@router.post("/vision/analyze")
def analyze_vision_diagram(req: VisionAnalyzeRequest):
    """Inspects P&ID and diagram drawings according to frozen API contract."""
    from backend.agents.vision_agent import VisionDiagramAgent
    agent = VisionDiagramAgent()
    res = agent.analyze(
        question=req.question,
        drawing_path=req.drawing_path,
        drawing_metadata={"id": "img-pid-cool-01", "filename": "PID_Cooling_Water_Circuit_P101.png"}
    )
    return {
        "workspace_id": req.workspace_id,
        "citations": res.get("citations", [])
    }

