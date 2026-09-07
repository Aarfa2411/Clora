"""
Unit tests for CalculationToolGateway.
Validates 3-tier routing: Deterministic Formulas, TabularEngine, and SecBox.
"""

import pytest
from backend.calculation.gateway import CalculationToolGateway
from backend.calculation.schemas import CalculationSourceType, CalculationConfidenceLevel


class TestCalculationGateway:
    def test_routes_reynolds_calculation(self):
        gateway = CalculationToolGateway()
        query = "Calculate the Reynolds number for pipe with diameter 0.25m, velocity 2.4m/s, density 860 kg/m3, and viscosity 0.0032 Pa.s"
        res = gateway.calculate(query)

        assert res.calculation_name == "Reynolds Number"
        assert res.source_type == CalculationSourceType.DETERMINISTIC_FORMULA
        assert res.confidence == CalculationConfidenceLevel.HIGH
        assert res.final_value == 161250.0
        assert res.verified is True
        assert len(res.steps) == 5

        # Test Evidence conversion
        evidence = res.to_evidence()
        assert evidence.chunk_id == res.calculation_id
        assert "Auditable Local Computation" in evidence.source_document
        assert "161250.0" in evidence.content

    def test_routes_lmtd_calculation(self):
        gateway = CalculationToolGateway()
        query = "Calculate LMTD for heat exchanger with T_hot_in 150, T_hot_out 100, T_cold_in 30, T_cold_out 90"
        res = gateway.calculate(query)

        assert res.calculation_name == "Log-Mean Temperature Difference (LMTD)"
        assert res.source_type == CalculationSourceType.DETERMINISTIC_FORMULA
        assert res.confidence == CalculationConfidenceLevel.HIGH
        assert res.final_value == 64.87

    def test_converts_to_presentation_markdown(self):
        gateway = CalculationToolGateway()
        query = "Calculate the Reynolds number for pipe with diameter 0.1, velocity 2.0, density 1000, viscosity 0.001"
        res = gateway.calculate(query)
        md = res.to_markdown()

        assert "### Auditable Calculation: Reynolds Number" in md
        assert "Governing Formula" in md
        assert "Step-by-Step Execution Trace" in md
        assert "Final Result" in md
