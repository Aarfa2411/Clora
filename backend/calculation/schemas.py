"""
Auditable Local Computation and Calculation Models for CLORA.
Defines machine-readable calculation traces, multi-factor confidence,
and typed calculation phases for sovereign industrial workflows.
SIH Problem Statement 26117 (MRPL)
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import hashlib
import json

from pydantic import BaseModel, Field
from backend.rag.evidence import Evidence


class CalculationPhase(str, Enum):
    INPUT = "INPUT"
    FORMULA = "FORMULA"
    CALCULATION = "CALCULATION"
    RESULT = "RESULT"
    VALIDATION = "VALIDATION"


class CalculationSourceType(str, Enum):
    DETERMINISTIC_FORMULA = "DETERMINISTIC_FORMULA"
    TABULAR_ENGINE = "TABULAR_ENGINE"
    LOCAL_SANDBOX_EXECUTION = "LOCAL_SANDBOX_EXECUTION"


class CalculationConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CalculationStep(BaseModel):
    step_number: int
    phase: CalculationPhase
    title: str
    description: str
    formula: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    value: Optional[float] = None
    unit: Optional[str] = None
    metric: Optional[str] = None
    source: Optional[str] = None
    raw_output: Optional[str] = None

    def to_display_line(self) -> str:
        val_str = f" = {self.value}" if self.value is not None else ""
        unit_str = f" {self.unit}" if self.unit else ""
        metric_str = f"{self.metric}: " if self.metric else ""
        return f"Step {self.step_number} [{self.phase.value}]: {self.title} — {metric_str}{self.description}{val_str}{unit_str}"


class StructuredCalculationResult(BaseModel):
    calculation_id: str
    calculation_name: str
    source_type: CalculationSourceType
    steps: List[CalculationStep] = Field(default_factory=list)
    final_metric: Optional[str] = None
    final_value: Optional[float] = None
    unit: Optional[str] = None
    confidence: CalculationConfidenceLevel = CalculationConfidenceLevel.MEDIUM
    confidence_rationale: str = ""
    formula_id: Optional[str] = None
    formula_expression: Optional[str] = None
    inputs_used: Dict[str, Any] = Field(default_factory=dict)
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    verified: bool = False
    validation_status: str = "PASSED"
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        """Generates an auditable, human-readable trace for engineering presentation."""
        lines = [
            f"### Auditable Calculation: {self.calculation_name}",
            f"**Source**: `{self.source_type.value}` | **Confidence**: `{self.confidence.value}` ({self.confidence_rationale})",
        ]
        if self.formula_expression:
            lines.append(f"**Governing Formula**: `{self.formula_expression}`")
        if self.final_value is not None:
            unit_str = f" {self.unit}" if self.unit else ""
            metric_str = f"{self.final_metric} = " if self.final_metric else ""
            lines.append(f"**Final Result**: **{metric_str}{self.final_value}{unit_str}**")

        lines.append("\n**Step-by-Step Execution Trace**:")
        for s in sorted(self.steps, key=lambda x: x.step_number):
            lines.append(f"- {s.to_display_line()}")

        if self.validation_status:
            lines.append(f"\n**Validation Status**: `{self.validation_status}`")
        return "\n".join(lines)

    def to_evidence(self) -> Evidence:
        """Converts calculation result into a first-class sovereign Evidence object."""
        step_summary = "; ".join(
            f"[{s.phase.value}] {s.title}: {s.value if s.value is not None else ''} {s.unit or ''}".strip()
            for s in sorted(self.steps, key=lambda x: x.step_number)
        )
        val_str = f"{self.final_value} {self.unit or ''}".strip()
        metric_str = f"{self.final_metric or self.calculation_name}: {val_str}"

        content = (
            f"Calculated {self.calculation_name}. {metric_str}. "
            f"Steps: {step_summary}. Status: {self.validation_status}. "
            f"Governing Formula: {self.formula_expression or 'N/A'}."
        )

        calc_hash = hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:12]
        return Evidence(
            evidence_id=f"ev_calc_{calc_hash}",
            content=content,
            source_document=f"Auditable Local Computation ({self.source_type.value})",
            page_number=1,
            chunk_id=self.calculation_id,
            relevance_score=1.0 if self.confidence == CalculationConfidenceLevel.HIGH else 0.85,
            equipment_id=self.inputs_used.get("equipment_id", ""),
            section="Engineering Calculation Trace",
            metadata={
                "source_type": self.source_type.value,
                "calculation_id": self.calculation_id,
                "calculation_name": self.calculation_name,
                "metric": self.final_metric or self.calculation_name,
                "final_value": self.final_value,
                "unit": self.unit,
                "confidence": self.confidence.value,
                "confidence_rationale": self.confidence_rationale,
                "formula_id": self.formula_id,
                "verified": self.verified,
                "steps_count": len(self.steps),
                "timestamp": self.timestamp,
            },
        )
