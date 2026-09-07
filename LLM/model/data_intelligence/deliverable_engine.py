"""
Unified Deliverable Package Engine for CLORA.
Renders evidence_manifest.json into Word (.docx), Excel (.xlsx), PowerPoint (.pptx), and ZIP packages.
"""

import os
import zipfile
from typing import Dict, Any, Optional

from .evidence_manifest import EvidenceManifestGenerator
from .docx_generator import ApprovalNoteGenerator
from .excel_generator import ExcelReportGenerator
from .ppt_generator import PPTReportGenerator


class DeliverableEngine:
    """Master Deliverable Gateway producing auditable evidence packages."""

    def __init__(self):
        self.manifest_gen = EvidenceManifestGenerator()
        self.docx_gen = ApprovalNoteGenerator()
        self.excel_gen = ExcelReportGenerator()
        self.ppt_gen = PPTReportGenerator()

    def generate_package(
        self,
        state: Dict[str, Any],
        output_dir: str = "output/deliverables",
        format_type: str = "all"
    ) -> Dict[str, Any]:
        """
        Build evidence_manifest.json and render requested formats.
        Format options: 'docx', 'xlsx', 'pptx', 'manifest', 'all', 'zip'
        """
        os.makedirs(output_dir, exist_ok=True)
        manifest = self.manifest_gen.build_manifest(state)
        
        manifest_path = os.path.join(output_dir, "evidence_manifest.json")
        self.manifest_gen.save_manifest(state, manifest_path)

        generated_files = {"evidence_manifest": manifest_path}

        if format_type in ["docx", "all", "zip"]:
            docx_path = os.path.join(output_dir, "investigation_report.docx")
            self.docx_gen.generate(manifest, output_path=docx_path)
            generated_files["docx"] = docx_path

        if format_type in ["xlsx", "all", "zip"]:
            xlsx_path = os.path.join(output_dir, "telemetry_audit.xlsx")
            self.excel_gen.generate(manifest, output_path=xlsx_path)
            generated_files["xlsx"] = xlsx_path

        if format_type in ["pptx", "all", "zip"]:
            pptx_path = os.path.join(output_dir, "executive_deck.pptx")
            self.ppt_gen.generate(manifest, output_path=pptx_path)
            generated_files["pptx"] = pptx_path

        if format_type in ["zip", "all"]:
            zip_path = os.path.join(output_dir, "clora_evidence_package.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_key, path in generated_files.items():
                    if os.path.exists(path):
                        zipf.write(path, arcname=os.path.basename(path))
            generated_files["zip_package"] = zip_path

        return {
            "status": "SUCCESS",
            "investigation_id": manifest["investigation_id"],
            "verification_score": manifest["verification"]["verification_score"],
            "generated_files": generated_files,
            "manifest": manifest,
        }
