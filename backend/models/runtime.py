"""
Model Runtime Manager for INDUSAI-X.
Manages Ollama REST inference, model pre-warming, health checking, and loud fallback.
"""

import time
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from backend.models.registry import (
    ModelRegistry,
    default_registry,
)


class GenerationResponse(BaseModel):
    text: str
    model_id: str
    latency_ms: float
    tokens_generated: int = 0
    is_fallback: bool = False
    warning: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelRuntimeManager:
    """Unified sovereign runtime interface for local models with loud fallback."""

    def __init__(
        self,
        ollama_base_url: str = "http://127.0.0.1:11434",
        registry: Optional[ModelRegistry] = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.registry = registry or default_registry

    def is_endpoint_reachable(self, timeout_sec: float = 0.5) -> bool:
        """Quickly checks if local Ollama daemon is reachable without hanging."""
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                res = client.get(f"{self.ollama_base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def list_pulled_models(self, timeout_sec: float = 1.0) -> List[str]:
        """Lists model tags currently downloaded and cached in Ollama."""
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                res = client.get(f"{self.ollama_base_url}/api/tags")
                if res.status_code == 200:
                    models = res.json().get("models", [])
                    return [m.get("name", "") for m in models]
        except Exception:
            pass
        return []

    def check_health(self) -> Dict[str, Any]:
        """Comprehensive operational health check of runtime and registered models."""
        reachable = self.is_endpoint_reachable()
        pulled = self.list_pulled_models() if reachable else []

        model_status = {}
        for m in self.registry.list_all():
            if m.is_fallback:
                model_status[m.model_id] = "ready_fallback"
            elif not reachable:
                model_status[m.model_id] = "offline_endpoint_down"
            elif any(m.model_id in tag for tag in pulled):
                model_status[m.model_id] = "ready_cached"
            else:
                model_status[m.model_id] = "missing_needs_pull"

        return {
            "endpoint": self.ollama_base_url,
            "reachable": reachable,
            "pulled_models_count": len(pulled),
            "pulled_models": pulled,
            "registered_models": model_status,
        }

    def prewarm_models(self, model_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Pre-warms specified models by executing a 1-token query.
        Caches model weights in RAM/VRAM to eliminate cold-load latency during live demo.
        """
        targets = model_ids or [
            m.model_id for m in self.registry.list_all() if not m.is_fallback
        ]
        results = {}
        if not self.is_endpoint_reachable():
            for mid in targets:
                results[mid] = False
            return results

        for mid in targets:
            try:
                with httpx.Client(timeout=httpx.Timeout(15.0, connect=1.0)) as client:
                    res = client.post(
                        f"{self.ollama_base_url}/api/generate",
                        json={"model": mid, "prompt": "1", "stream": False, "options": {"num_predict": 1}},
                    )
                    results[mid] = res.status_code == 200
            except Exception:
                results[mid] = False
        return results

    def generate(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> GenerationResponse:
        """
        Generates text using the requested model.
        If the model or endpoint is unreachable, executes LOUD deterministic fallback.
        """
        start_time = time.time()
        profile = self.registry.get(model_id)

        # 1. If explicitly requesting mock, go direct to fallback
        if profile and profile.is_fallback:
            return self._execute_loud_fallback(model_id, prompt, start_time, reason="Requested mock engine directly")

        # 2. Try Ollama execution
        if profile and profile.provider == "ollama":
            if not self.is_endpoint_reachable(timeout_sec=0.25):
                return self._execute_loud_fallback(
                    model_id, prompt, start_time, reason=f"Ollama daemon unreachable at {self.ollama_base_url}"
                )

            timeout_sec = profile.timeout_seconds or 10.0
            try:
                payload = {
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                }
                if system_prompt:
                    payload["system"] = system_prompt

                with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=1.0)) as client:
                    res = client.post(f"{self.ollama_base_url}/api/generate", json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        text = data.get("response", "").strip()
                        latency_ms = (time.time() - start_time) * 1000
                        return GenerationResponse(
                            text=text,
                            model_id=model_id,
                            latency_ms=round(latency_ms, 2),
                            tokens_generated=len(text.split()),
                            is_fallback=False,
                            warning=None,
                        )
            except Exception as e:
                # Log Loud Fallback Activation
                return self._execute_loud_fallback(
                    model_id, prompt, start_time, reason=f"Ollama execution failed: {str(e)}"
                )

        # 3. Fallback for unknown provider
        return self._execute_loud_fallback(
            model_id, prompt, start_time, reason=f"Unknown or unconfigured model provider for {model_id}"
        )

    def _execute_loud_fallback(
        self, target_model: str, prompt: str, start_time: float, reason: str
    ) -> GenerationResponse:
        """Executes deterministic offline fallback with prominent warning telemetry."""
        latency_ms = (time.time() - start_time) * 1000
        warning_msg = (
            f"[FALLBACK MODE ACTIVE - NOT LIVE INFERENCE: '{target_model}' offline ({reason})]"
        )
        print(f"\n{'='*78}\n  WARNING: {warning_msg}\n{'='*78}\n")

        p_lower = prompt.lower()
        if "def " in prompt or "import " in prompt or "code" in p_lower or "calculate" in p_lower:
            # Deterministic code synthesis fallback
            text = (
                "import os, json\n"
                "# Generated deterministic analytics script with machine-readable trace\n"
                "def analyze_telemetry():\n"
                "    in_dir = os.environ.get('INDUSAI_SANDBOX_INPUT', '/workspace/input')\n"
                "    out_dir = os.environ.get('INDUSAI_SANDBOX_OUTPUT', '/workspace/output')\n"
                "    os.makedirs(out_dir, exist_ok=True)\n"
                "    csv_path = os.path.join(in_dir, 'telemetry.csv')\n"
                "    peak_temp, rms_vib = 104.2, 9.82\n"
                "    if os.path.exists(csv_path):\n"
                "        try:\n"
                "            import pandas as pd\n"
                "            df = pd.read_csv(csv_path)\n"
                "            peak_temp = float(df['inboard_bearing_temp_c'].max()) if 'inboard_bearing_temp_c' in df.columns else 104.2\n"
                "            rms_vib = float(df['vibration_velocity_rms'].max()) if 'vibration_velocity_rms' in df.columns else 9.82\n"
                "        except ImportError:\n"
                "            pass\n"
                "    print(f'MAX_TEMPERATURE: {peak_temp:.1f} C')\n"
                "    print(f'MAX_VIBRATION_RMS: {rms_vib:.2f} mm/s')\n"
                "    payload = {\n"
                "        'calculation_id': 'CALC-FALLBACK-01',\n"
                "        'calculation_name': 'Telemetry Sensor Excursion',\n"
                "        'source_type': 'LOCAL_SANDBOX_EXECUTION',\n"
                "        'final_metric': 'Peak Inboard Bearing Temperature',\n"
                "        'final_value': peak_temp,\n"
                "        'unit': 'degC',\n"
                "        'confidence': 'HIGH',\n"
                "        'confidence_rationale': 'Deterministic offline telemetry evaluation.',\n"
                "        'steps': [\n"
                "            {'step_number': 1, 'phase': 'INPUT', 'title': 'Data Ingestion', 'description': 'Loaded telemetry records', 'value': peak_temp, 'unit': 'degC'},\n"
                "            {'step_number': 2, 'phase': 'RESULT', 'title': 'Excursion Evaluation', 'description': f'Peak Temp: {peak_temp:.1f} C, Peak Vibration: {rms_vib:.2f} mm/s', 'value': peak_temp, 'unit': 'degC'}\n"
                "        ]\n"
                "    }\n"
                "    with open(os.path.join(out_dir, 'calculation_result.json'), 'w', encoding='utf-8') as f:\n"
                "        json.dump(payload, f, indent=2)\n"
                "    return peak_temp, rms_vib\n\n"
                "if __name__ == '__main__':\n"
                "    analyze_telemetry()\n"
            )
        elif "why" in p_lower or "failure" in p_lower or "root cause" in p_lower:
            # Deterministic RCA synthesis fallback
            text = (
                "ANSWER\n"
                "────────────────────────\n"
                "Verified Findings\n"
                "• Inboard bearing temperature excursion exceeded threshold of 80.0°C. [Source: Maintenance_Report.pdf, Page 14]\n"
                "• Lube oil pressure dropped to 0.4 bar prior to equipment trip. [Source: Inspection_Log.pdf, Page 3]\n\n"
                "Analysis\n"
                "• Available records indicate dry friction and thermal excursion on Pump P-101 inboard roller bearing.\n\n"
                "Uncertainty\n"
                "• The records do not establish whether external mechanical misalignment contributed.\n\n"
                "Confidence: MEDIUM\n\n"
                "Evidence\n"
                "[1] Maintenance_Report.pdf — Page 14\n"
                "[2] Inspection_Log.pdf — Page 3"
            )
        else:
            text = "Deterministic industrial synthesis verified from authorized knowledge repository."

        return GenerationResponse(
            text=text,
            model_id="deterministic-airgap-mock",
            latency_ms=round(latency_ms, 2),
            tokens_generated=len(text.split()),
            is_fallback=True,
            warning=warning_msg,
            metadata={"requested_model": target_model, "fallback_reason": reason},
        )


default_runtime = ModelRuntimeManager()
