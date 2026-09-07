"""
Production-Hardened PDF & Scanned Document Extractor.
INDUSAI-X / SIH Problem Statement 26117 (MRPL)
Member 6: Data Intelligence + Knowledge Graph + Security Engineer

Features:
- Dual-engine extraction: High-speed native PyMuPDF stream + Preprocessed OCR fallback.
- Auto-triage: Classifies each page as Native Text, Scanned Raster, or Mixed Hybrid.
- Integrated Industrial Image Preprocessing (Deskew, CLAHE contrast, Denoising).
- Baseline-normalized spatial table reconstruction and key-value form extraction.
- Human-in-the-loop confidence assessment (<60% flagged for review).
- Streaming & memory-bounded page processing (explicit pixmap cleanup).
- Structured RAG chunk segmentation (DocumentChunk) with rich OCR metadata.
- Local VLM dispatch hook for unstructured handwriting and engineering drawings.
"""

import os
import io
import gc
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
import pymupdf as fitz
from PIL import Image

from .models import (
    PageExtraction,
    DocumentExtractionResult,
    DocumentChunk
)
from .ocr_pipeline import (
    ImagePreprocessor,
    TesseractOCREngine,
    SpatialTableReconstructor,
    OCRQualityAssessor,
    PlantEntityValidator
)

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def reconstruct_table_from_ocr_data(
    ocr_data: Dict[str, List[Any]],
    y_tolerance: float = 8.0
) -> List[List[str]]:
    """Legacy backward-compatible adapter for table reconstruction."""
    return SpatialTableReconstructor.reconstruct_table(ocr_data, y_tolerance=y_tolerance)


def extract_handwritten_via_vlm(image_bytes: bytes, prompt: str = "Transcribe handwritten industrial notes") -> str:
    """Dispatches complex unstructured handwriting and P&ID diagrams to local VLM server."""
    engine = TesseractOCREngine()
    return engine.dispatch_vlm_handwriting(image_bytes, prompt=prompt)


class DocumentExtractor:
    """Production dual-engine PDF extraction and RAG chunking pipeline."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.ocr_engine = TesseractOCREngine(tesseract_cmd=tesseract_cmd)

    def _extract_page_ocr(
        self,
        page: fitz.Page,
        dpi: int = 200,
        auto_deskew: bool = True
    ) -> Tuple[str, List[List[str]], List[Dict[str, Any]], float, List[Dict[str, Any]], float, bool, str, str]:
        """
        Renders a page pixmap, applies image preprocessing (deskew/enhance), and executes OCR.
        Returns: (text, tables, blocks, mean_confidence, word_boxes, skew_angle, needs_review, tier, engine_mode)
        """
        zoom = dpi / 72.0
        raw_img = ImagePreprocessor.rasterize_page(page, dpi=dpi)

        try:
            enhanced_img, skew_angle = ImagePreprocessor.deskew_and_enhance(
                raw_img,
                auto_deskew=auto_deskew,
                enhance_contrast=True,
                denoise=True
            )

            text, tables, blocks, mean_conf, word_boxes, needs_review, tier, engine_mode = self.ocr_engine.process_image(
                enhanced_img,
                psm=3,
                zoom_ratio=zoom
            )

            return text, tables, blocks, mean_conf, word_boxes, skew_angle, needs_review, tier, engine_mode

        except Exception as e:
            logger.error("Page OCR extraction error: %s", e)
            fallback_text = f"[OCR Extraction Unavailable: {str(e)}]"
            return fallback_text, [], [], 0.0, [], 0.0, True, "TIER_4_MANDATORY_REVIEW", "DEVELOPMENT_TEST_MOCK"
        finally:
            del raw_img
            gc.collect()

    def _segment_rag_chunks(
        self,
        doc_id: str,
        filename: str,
        page_num: int,
        text: str,
        tables: List[List[List[str]]],
        blocks: List[Dict[str, Any]],
        extraction_method: str,
        ocr_conf: Optional[float],
        tier: str,
        entity_warnings: List[str]
    ) -> List[DocumentChunk]:
        """
        Segments extracted page content into structured chunks with heading levels,
        bounding boxes, entity validation warnings, and OCR metadata for Member 5's RAG embeddings.
        """
        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        current_offset = 0

        for para in paragraphs:
            heading_level = None
            block_type = "paragraph" if extraction_method == "native_text" else "ocr_block"

            lines = para.split("\n")
            first_line = lines[0].strip()
            if len(first_line) < 80 and (first_line[0].isdigit() or first_line.isupper()):
                heading_level = 1 if first_line[0].isdigit() else 2
                block_type = "header"

            chunk_id = f"{doc_id}_P{page_num}_C{chunk_idx}"
            chunk_len = len(para)

            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                page_number=page_num,
                block_type=block_type,
                heading_level=heading_level,
                text=para,
                char_offset_start=current_offset,
                char_offset_end=current_offset + chunk_len,
                bbox=[],
                metadata={
                    "word_count": len(para.split()),
                    "extraction_method": extraction_method,
                    "confidence_tier": tier
                },
                source_document=filename,
                ocr_confidence=ocr_conf,
                extraction_method=extraction_method,
                confidence_tier=tier,
                entity_warnings=entity_warnings
            ))
            current_offset += chunk_len + 2
            chunk_idx += 1

        for t_idx, table in enumerate(tables):
            table_md = "\n".join([" | ".join(str(cell) for cell in row) for row in table])
            chunk_text = f"Table {t_idx + 1}:\n{table_md}"
            chunks.append(DocumentChunk(
                chunk_id=f"{doc_id}_P{page_num}_T{t_idx}",
                page_number=page_num,
                block_type="table",
                heading_level=None,
                text=chunk_text,
                char_offset_start=current_offset,
                char_offset_end=current_offset + len(chunk_text),
                bbox=[],
                metadata={
                    "rows": len(table),
                    "cols": len(table[0]) if table else 0,
                    "extraction_method": extraction_method,
                    "confidence_tier": tier
                },
                source_document=filename,
                ocr_confidence=ocr_conf,
                extraction_method=extraction_method,
                confidence_tier=tier,
                entity_warnings=entity_warnings
            ))

        return chunks

    def extract(self, pdf_path: str, auto_deskew: bool = True, dpi: int = 200) -> DocumentExtractionResult:
        """
        Extracts document text, metadata, tables, and RAG chunks.
        Performs hybrid and OCR auto-triage routing per page with plant entity validation.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF document not found: {pdf_path}")

        doc_id = compute_file_sha256(pdf_path)[:16]
        filename = os.path.basename(pdf_path)
        doc = fitz.open(pdf_path)

        metadata = {
            "title": doc.metadata.get("title", filename),
            "author": doc.metadata.get("author", "MRPL"),
            "subject": doc.metadata.get("subject", "Refinery Report"),
            "page_count": len(doc),
            "format": doc.metadata.get("format", "PDF 1.7")
        }

        extracted_pages: List[PageExtraction] = []
        all_chunks: List[DocumentChunk] = []
        all_methods = set()
        overall_needs_review = False
        all_confidences = []
        scanned_count = 0
        digital_count = 0
        doc_entity_warnings = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1

            native_text = page.get_text().strip()
            images = page.get_images()
            char_count = len(native_text)
            skew_angle = 0.0
            word_boxes = []
            ocr_engine_name = "native_stream"
            tier = "TIER_1_HIGH_CONFIDENCE"

            if char_count >= 50 and len(images) == 0:
                method = "native_text"
                page_text = native_text
                ocr_conf = None
                needs_review = False
                digital_count += 1
                ocr_engine_name = "native_pymupdf"
                tier = "TIER_1_HIGH_CONFIDENCE"

                tables_raw = page.find_tables()
                tables = [t.extract() for t in tables_raw] if tables_raw else []

                page_blocks = page.get_text("blocks")
                blocks = [{"bbox": list(b[:4]), "text": b[4], "type": "native_text"} for b in page_blocks]

            elif char_count < 50:
                method = "ocr_fallback"
                scanned_count += 1
                page_text, tables, blocks, ocr_conf, word_boxes, skew_angle, needs_review, tier, ocr_engine_name = self._extract_page_ocr(
                    page, dpi=dpi, auto_deskew=auto_deskew
                )
                char_count = len(page_text)
                if ocr_conf is not None:
                    all_confidences.append(ocr_conf)

            else:
                method = "hybrid"
                scanned_count += 1
                ocr_text, ocr_tables, ocr_blocks, ocr_conf, word_boxes, skew_angle, needs_review, tier, ocr_engine_name = self._extract_page_ocr(
                    page, dpi=dpi, auto_deskew=auto_deskew
                )
                page_text = f"{native_text}\n\n[Embedded Scanned Content / Stamp]:\n{ocr_text}"
                tables = ocr_tables
                blocks = ocr_blocks
                char_count = len(page_text)
                if ocr_conf is not None:
                    all_confidences.append(ocr_conf)

            # Plant Entity Validation Check
            val_res = PlantEntityValidator.validate_equipment_tags(page_text)
            page_warnings = val_res.get("warnings", [])
            doc_entity_warnings.extend(page_warnings)

            if method in ("ocr_fallback", "hybrid") and val_res.get("has_warnings"):
                needs_review = True

            all_methods.add(method)
            if needs_review:
                overall_needs_review = True

            page_chunks = self._segment_rag_chunks(
                doc_id=doc_id,
                filename=filename,
                page_num=page_num,
                text=page_text,
                tables=tables,
                blocks=blocks,
                extraction_method=method,
                ocr_conf=ocr_conf,
                tier=tier,
                entity_warnings=page_warnings
            )
            all_chunks.extend(page_chunks)

            extracted_pages.append(PageExtraction(
                page_number=page_num,
                text=page_text,
                char_count=char_count,
                extraction_method=method,
                tables=tables,
                blocks=blocks,
                chunks=page_chunks,
                ocr_confidence=ocr_conf,
                needs_human_review=needs_review,
                skew_angle=skew_angle,
                ocr_engine=ocr_engine_name,
                word_boxes=word_boxes,
                confidence_tier=tier,
                entity_warnings=page_warnings
            ))

        doc.close()

        if len(all_methods) == 1:
            primary_method = list(all_methods)[0]
        elif "ocr_fallback" in all_methods and "native_text" in all_methods:
            primary_method = "hybrid"
        else:
            primary_method = "hybrid" if "hybrid" in all_methods else "native_text"

        overall_conf = (
            round(sum(all_confidences) / len(all_confidences), 1)
            if all_confidences
            else None
        )

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(p.text for p in extracted_pages)

        return DocumentExtractionResult(
            document_id=doc_id,
            filename=filename,
            file_path=pdf_path,
            total_pages=len(extracted_pages),
            primary_method=primary_method,
            metadata=metadata,
            pages=extracted_pages,
            chunks=all_chunks,
            full_text=full_text,
            needs_human_review=overall_needs_review,
            overall_ocr_confidence=overall_conf,
            scanned_page_count=scanned_count,
            digital_page_count=digital_count,
            entity_warnings=doc_entity_warnings
        )


def extract_pdf(pdf_path: str, auto_deskew: bool = True, dpi: int = 200) -> DocumentExtractionResult:
    """Convenience top-level function to extract any digital, scanned, or hybrid PDF."""
    extractor = DocumentExtractor()
    return extractor.extract(pdf_path, auto_deskew=auto_deskew, dpi=dpi)
