"""
Unit tests for Deterministic Engineering Formulas.
Validates zero-hallucination mathematical execution, step phases, and boundary checks.
"""

import pytest
from backend.calculation.formulas import (
    compute_reynolds_number,
    compute_lmtd_counterflow,
    compute_haaland_friction_factor,
    compute_vibration_rms_severity,
)
from backend.calculation.schemas import (
    CalculationConfidenceLevel,
    CalculationPhase,
    CalculationSourceType,
)


class TestCalculationFormulas:
    def test_reynolds_number_turbulent(self):
        inputs = {
            "density": 1000.0,
            "velocity": 2.5,
            "diameter": 0.1,
            "viscosity": 0.001,
        }
        res = compute_reynolds_number(inputs)
        assert res.verified is True
        assert res.confidence == CalculationConfidenceLevel.HIGH
        assert res.source_type == CalculationSourceType.DETERMINISTIC_FORMULA
        assert res.final_value == 250000.0
        assert res.unit == "dimensionless"
        assert len(res.steps) == 5

        # Check step sequence
        phases = [s.phase for s in res.steps]
        assert phases == [
            CalculationPhase.INPUT,
            CalculationPhase.FORMULA,
            CalculationPhase.CALCULATION,
            CalculationPhase.RESULT,
            CalculationPhase.VALIDATION,
        ]
        assert "Turbulent Flow" in res.steps[3].description

    def test_reynolds_number_laminar(self):
        inputs = {
            "density": 900.0,
            "velocity": 0.5,
            "diameter": 0.05,
            "viscosity": 0.05,
        }
        res = compute_reynolds_number(inputs)
        assert res.verified is True
        assert res.final_value == 450.0
        assert "Laminar Flow" in res.steps[3].description

    def test_reynolds_invalid_negative_input(self):
        inputs = {"density": -100.0, "velocity": 1.0, "diameter": 0.1, "viscosity": 0.001}
        res = compute_reynolds_number(inputs)
        assert res.verified is False
        assert res.confidence == CalculationConfidenceLevel.LOW
        assert "FAILED" in res.validation_status

    def test_lmtd_counterflow(self):
        inputs = {
            "t_hot_in": 150.0,
            "t_hot_out": 100.0,
            "t_cold_in": 30.0,
            "t_cold_out": 90.0,
        }
        # Delta T1 = 150 - 90 = 60
        # Delta T2 = 100 - 30 = 70
        # LMTD = (60 - 70) / ln(60/70) = -10 / -0.15415 = 64.86
        res = compute_lmtd_counterflow(inputs)
        assert res.verified is True
        assert res.confidence == CalculationConfidenceLevel.HIGH
        assert res.final_value == 64.87
        assert res.unit == "degC"
        assert len(res.steps) == 5

    def test_haaland_friction_factor_turbulent(self):
        inputs = {"reynolds": 100000.0, "diameter": 0.2, "roughness": 0.000045}
        res = compute_haaland_friction_factor(inputs)
        assert res.verified is True
        assert res.confidence == CalculationConfidenceLevel.HIGH
        # Typical Darcy friction factor for Re=10^5 is around 0.018 - 0.022
        assert 0.015 <= res.final_value <= 0.025

    def test_vibration_rms_zone_d(self):
        inputs = {"vibration_rms": 9.82}
        res = compute_vibration_rms_severity(inputs)
        assert res.verified is True
        assert res.final_value == 9.82
        assert res.unit == "mm/s"
        assert res.validation_status == "ALARM_EXCEEDED"
        assert any("Zone D" in s.description for s in res.steps)
