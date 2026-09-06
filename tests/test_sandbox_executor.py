"""
Unit tests for Sandbox Executor.
"""

import os
import pytest
from backend.sandbox.docker_executor import SandboxExecutor


class TestSandboxExecutor:
    def test_run_simple_stdout_script(self):
        executor = SandboxExecutor(timeout_sec=5.0)
        code = (
            "a = 10\n"
            "b = 25\n"
            "print(f'CALCULATION_RESULT: {a + b}')\n"
        )
        res = executor.run(code)
        assert res.exit_code == 0
        assert "CALCULATION_RESULT: 35" in res.stdout
        assert res.execution_time_ms > 0

    def test_timeout_stops_infinite_loop(self):
        # Set a short 1-second timeout
        executor = SandboxExecutor(timeout_sec=1.0)
        code = (
            "import time\n"
            "while True:\n"
            "    time.sleep(0.1)\n"
        )
        res = executor.run(code)
        assert res.exit_code == -1
        assert "timed out" in res.stderr.lower()

    def test_generates_file_into_output_directory(self):
        executor = SandboxExecutor(timeout_sec=5.0)
        code = (
            "import os\n"
            "# Discover output directory (either Docker mount /workspace/output or dev env)\n"
            "out_dir = os.environ.get('INDUSAI_SANDBOX_OUTPUT', '/workspace/output')\n"
            "os.makedirs(out_dir, exist_ok=True)\n"
            "target = os.path.join(out_dir, 'telemetry_metrics.txt')\n"
            "with open(target, 'w') as f:\n"
            "    f.write('PEAK_RMS: 9.82')\n"
            "print('METRICS_WRITTEN')\n"
        )
        res = executor.run(code)
        assert res.exit_code == 0
        assert "METRICS_WRITTEN" in res.stdout
        assert len(res.generated_files) >= 1
        assert any("telemetry_metrics.txt" in f for f in res.generated_files)
