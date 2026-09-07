"""
Unit & Integration Tests for Multimodal Engineering Drawing Intelligence.
INDUSAI-X / SIH26117 (MRPL)
"""

import os
import pytest
from PIL import Image

from indusai.multimodal.schema import (
    BoundingBox,
    ConfidenceLevel,
    EvidenceType,
    DetectedEntity,
    PipingEdge,
    DrawingAnalysisResult,
)
from indusai.multimodal.adaptive_tiler import AdaptiveTiler
from indusai.multimodal.cv_engine import DrawingCVEngine, normalize_fuzzy_tag
from indusai.multimodal.vlm_bridge import VLMBridge, DeterministicRuleProvider
from indusai.multimodal.evidence_fusion import EvidenceFusionEngine
from indusai.multimodal.connectivity_tracer import StagedConnectivityTracer
from data_intelligence.knowledge_graph import RefineryKnowledgeGraph
from backend.agents.vision_agent import VisionDiagramAgent


@pytest.fixture
def sample_drawing_path():
    path = os.path.join("samples", "PID_Cooling_Water_Circuit_P101.png")
    if not os.path.exists(path):
        from samples.generate_sample_pid import generate_sample_pid
        path = generate_sample_pid(path)
    return path


def test_bounding_box_coordinates():
    bbox = BoundingBox(ymin=0.1, xmin=0.2, ymax=0.5, xmax=0.6)
    assert bbox.to_list() == [0.1, 0.2, 0.5, 0.6]

    px_box = bbox.to_pixel_box(width=1000, height=800)
    assert px_box["x"] == 200
    assert px_box["y"] == 80
    assert px_box["width"] == 400
    assert px_box["height"] == 320

    converted = BoundingBox.from_pixel_coords(200, 80, 400, 320, 1000, 800)
    assert round(converted.xmin, 2) == 0.2
    assert round(converted.ymin, 2) == 0.1


def test_adaptive_tiler_grid_and_crops(sample_drawing_path):
    tiler = AdaptiveTiler(target_tile_size=1024, overlap_ratio=0.15)
    img = Image.open(sample_drawing_path)
    w, h = img.size

    grid_spec = tiler.compute_grid_spec(w, h)
    assert grid_spec["width"] == w
    assert grid_spec["height"] == h
    assert len(grid_spec["cells"]) >= 4

    # Test coordinate mapping to grid cell
    center_bbox = BoundingBox(ymin=0.5, xmin=0.5, ymax=0.6, xmax=0.6)
    cell = tiler.get_grid_cell(center_bbox, grid_spec)
    assert "Grid" in cell

    # Test focused cropping
    crop, crop_bbox = tiler.crop_for_bbox(img, center_bbox, padding_ratio=0.05)
    assert crop.width > 0
    assert crop.height > 0
    assert crop_bbox.xmin <= center_bbox.xmin
    assert crop_bbox.xmax >= center_bbox.xmax

    # Test base64 encoding
    b64 = tiler.image_to_base64(crop)
    assert len(b64) > 50
    decoded = tiler.base64_to_image(b64)
    assert decoded.size == crop.size


def test_fuzzy_ocr_tag_normalization():
    # Common OCR letter/digit confusions
    assert normalize_fuzzy_tag("CV", "IO4", "B") == ("CV-104B", "control_valve")
    assert normalize_fuzzy_tag("P", "IO1", "") == ("P-101", "pump")
    assert normalize_fuzzy_tag("V", "IO9", "") == ("V-109", "valve")
    assert normalize_fuzzy_tag("HEX", "3O1", "") == ("HEX-301", "exchanger")
    assert normalize_fuzzy_tag("PT", "2O1", "") == ("PT-201", "transmitter")
    # Non-standard prefix rejected
    assert normalize_fuzzy_tag("INVALID", "123", "") is None


def test_cv_engine_entity_detection(sample_drawing_path):
    cv = DrawingCVEngine()
    img, w, h = cv.load_drawing_image(sample_drawing_path)
    assert w > 500
    assert h > 500

    entities = cv.scan_image_for_entities(img)
    tags = [e.tag for e in entities]
    assert "P-101" in tags
    assert "CV-104B" in tags
    assert "V-109" in tags

    v109 = next(e for e in entities if e.tag == "V-109")
    assert v109.state == "NC"
    assert v109.confidence == ConfidenceLevel.HIGH


def test_vlm_bridge_focused_crop_queries(sample_drawing_path):
    bridge = VLMBridge(provider=DeterministicRuleProvider())
    img = Image.open(sample_drawing_path)

    # Test V-109 focused crop query
    v109_crop = img.crop((600, 600, 1000, 900))
    res = bridge.query_crop(v109_crop, "What is the status of valve V-109?", context_tags=["V-109"])
    assert res["tag"] == "V-109"
    assert res["state"] == "NC"
    assert "normally closed" in res["description"].lower() or "nc" in res["description"].lower()


def test_evidence_fusion_engine(sample_drawing_path):
    engine = EvidenceFusionEngine()
    result = engine.analyze_drawing(
        file_path=sample_drawing_path,
        user_query="What valve is on the bypass line and what is its state?"
    )

    assert isinstance(result, DrawingAnalysisResult)
    assert len(result.entities) >= 3
    assert len(result.visual_evidence) >= 2

    # Check evidence types
    evidence_types = {ev.evidence_type for ev in result.visual_evidence}
    assert EvidenceType.TAG in evidence_types
    assert EvidenceType.SYMBOL in evidence_types

    # Check that crops have base64 data
    for ev in result.visual_evidence:
        assert ev.crop_base64 is not None
        assert len(ev.crop_base64) > 20
        assert "Grid" in ev.grid_cell


def test_staged_connectivity_tracer():
    tracer = StagedConnectivityTracer()
    p101 = DetectedEntity(
        tag="P-101",
        component_type="pump",
        state="OPERATING",
        grid_cell="Grid C2",
        symbol_bbox=BoundingBox(ymin=0.40, xmin=0.20, ymax=0.50, xmax=0.30)
    )
    cv104b = DetectedEntity(
        tag="CV-104B",
        component_type="control_valve",
        state="OPERATING",
        grid_cell="Grid D4",
        symbol_bbox=BoundingBox(ymin=0.42, xmin=0.40, ymax=0.48, xmax=0.46)
    )
    v109 = DetectedEntity(
        tag="V-109",
        component_type="valve",
        state="NC",
        grid_cell="Grid D4",
        symbol_bbox=BoundingBox(ymin=0.52, xmin=0.40, ymax=0.58, xmax=0.46)
    )

    edges = tracer.trace_candidate_connections([p101, cv104b, v109])
    assert len(edges) >= 1

    # Check parallel bypass loop edge between CV-104B and V-109
    bypass_edge = next((e for e in edges if e.source_tag == "CV-104B" and e.target_tag == "V-109"), None)
    assert bypass_edge is not None
    assert bypass_edge.is_validated is True
    assert bypass_edge.flow_direction == "BIDIRECTIONAL"


def test_knowledge_graph_provenance_integration():
    kg = RefineryKnowledgeGraph()
    edge = PipingEdge(
        source_tag="P-101",
        target_tag="CV-104B",
        line_spec='4"-CW-102-CS',
        flow_direction="FORWARD",
        confidence=ConfidenceLevel.HIGH,
        is_validated=True,
        provenance={"source_drawing": "PID_Cooling_Water_Circuit_P101.png", "grid": "Grid D4"}
    )

    added = kg.ingest_drawing_edges([edge])
    assert added == 1

    # Verify edge stored in NetworkX graph with full provenance
    assert kg.graph.has_edge("P-101", "CV-104B")
    edge_data = kg.graph.get_edge_data("P-101", "CV-104B")
    assert edge_data["provenance_source"] == "PID_Cooling_Water_Circuit_P101.png"
    assert edge_data["grid_location"] == "Grid D4"
    assert edge_data["is_validated"] is True


def test_vision_diagram_agent_contracts(sample_drawing_path):
    agent = VisionDiagramAgent()
    res = agent.analyze(
        question="What valve is on the bypass line of Pump P-101?",
        drawing_path=sample_drawing_path,
        drawing_metadata={"id": "img-pid-01", "filename": "PID_Cooling_Water_Circuit_P101.png"}
    )

    assert "citations" in res
    citations = res["citations"]
    assert len(citations) >= 1

    c = citations[0]
    assert c["file_type"] == "image"
    assert "Grid D4" in c["sheet_or_table"] or "P&ID" in c["sheet_or_table"]
    assert "CV-104B" in c["snippet_or_data"] or "V-109" in c["snippet_or_data"]
    assert c["confidence"] >= 0.90
    assert c["file_available"] is True
