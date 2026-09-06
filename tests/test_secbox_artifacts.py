"""
Unit tests for CLORA-SecBox Artifact Inspector & Quota Enforcement.
"""

import os
import tempfile

from backend.sandbox.artifact_inspector import ArtifactInspector


class TestSecBoxArtifactInspector:
    def setup_method(self):
        self.inspector = ArtifactInspector(max_files=3, max_total_size_mb=1.0)

    def test_file_count_quota_exceeded(self):
        with tempfile.TemporaryDirectory() as td:
            files = []
            for i in range(5):  # Limit is 3
                fp = os.path.join(td, f"file_{i}.csv")
                with open(fp, "w") as f:
                    f.write("a,b,c\n1,2,3\n")
                files.append(fp)

            res = self.inspector.inspect(files)
            assert res.valid is False
            assert any("file count quota exceeded" in v.lower() for v in res.violations)

    def test_disallowed_extension_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "script.sh")
            with open(fp, "w") as f:
                f.write("#!/bin/bash\necho hello\n")

            res = self.inspector.inspect([fp])
            assert res.valid is False
            assert any("disallowed file extension" in v.lower() for v in res.violations)

    def test_spoofed_png_magic_byte_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            # Text file masquerading as a .png
            fp = os.path.join(td, "malicious_chart.png")
            with open(fp, "wb") as f:
                f.write(b"this is plain text not real PNG")

            res = self.inspector.inspect([fp])
            assert res.valid is False
            assert any("corrupt or spoofed png magic header" in v.lower() for v in res.violations)

    def test_valid_png_and_csv_approved_with_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            # Valid PNG header
            png_fp = os.path.join(td, "vibration_chart.png")
            with open(png_fp, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (b"\x00" * 50))

            # Valid CSV
            csv_fp = os.path.join(td, "summary.csv")
            with open(csv_fp, "w", encoding="utf-8") as f:
                f.write("metric,value\npeak_temp,104.2\n")

            res = self.inspector.inspect([png_fp, csv_fp])
            assert res.valid is True
            assert len(res.approved_files) == 2
            assert "vibration_chart.png" in res.artifact_hashes
            assert "summary.csv" in res.artifact_hashes
            assert len(res.artifact_hashes["vibration_chart.png"]) == 64
