"""
Unit and Adversarial Security Tests for Spreadsheet & Engineering Calculation Engine.
Validates:
- Excel .xlsx and CSV safe parsing
- AST SQL Injection defense (multi-statement, non-SELECT, filesystem functions)
- Query pagination and explicit truncation metadata
- Deterministic engineering calculation suite (Reynolds number, Vibration RMS, Pump Head, Thermal Efficiency)
- Cryptographic data lineage tracking
"""

import tempfile
import pandas as pd
import pytest

from backend.app.core.tool_authorization import ActorContext
from backend.app.services.spreadsheet_service import (
    CalculationResult,
    SpreadsheetService,
)


@pytest.fixture
def test_actor():
    return ActorContext(
        actor_type="user",
        actor_id="eng_01",
        role="engineer",
        department="operations",
        session_id="sess_01",
    )


@pytest.fixture
def sample_telemetry_df():
    return pd.DataFrame({
        "timestamp": ["2026-09-01T10:00:00Z", "2026-09-01T10:01:00Z", "2026-09-01T10:02:00Z", "2026-09-01T10:03:00Z"],
        "equipment_id": ["P-101", "P-101", "P-102", "P-102"],
        "bearing_temp_c": [74.2, 78.5, 65.1, 66.0],
        "discharge_pressure_bar": [8.4, 8.6, 12.1, 12.0],
        "vibration_rms_mms": [2.4, 2.8, 1.8, 1.9],
    })


def test_safe_sql_query_execution(test_actor, sample_telemetry_df):
    ws_id = "ws_test_sheet"
    query = "SELECT equipment_id, AVG(bearing_temp_c) as avg_temp FROM telemetry GROUP BY equipment_id ORDER BY avg_temp DESC"

    res = SpreadsheetService.execute_safe_query(
        actor=test_actor,
        workspace_id=ws_id,
        table_name="telemetry",
        df=sample_telemetry_df,
        sql_query=query,
    )

    assert res["table_name"] == "telemetry"
    assert res["total_matching_rows"] == 2
    assert len(res["rows"]) == 2
    assert res["truncated"] is False
    assert len(res["query_hash"]) == 64
    assert len(res["result_hash"]) == 64


def test_sql_injection_and_prohibited_statements_blocked(test_actor, sample_telemetry_df):
    ws_id = "ws_test_sheet"

    # Multi-statement injection attempt
    with pytest.raises(ValueError, match="Multi-statement"):
        SpreadsheetService.execute_safe_query(
            actor=test_actor,
            workspace_id=ws_id,
            table_name="telemetry",
            df=sample_telemetry_df,
            sql_query="SELECT * FROM telemetry; DROP TABLE telemetry;",
        )

    # Prohibited modification statement
    with pytest.raises(ValueError, match="Only read-only SELECT queries are allowed"):
        SpreadsheetService.execute_safe_query(
            actor=test_actor,
            workspace_id=ws_id,
            table_name="telemetry",
            df=sample_telemetry_df,
            sql_query="DELETE FROM telemetry WHERE equipment_id = 'P-101'",
        )

    # Prohibited filesystem access function
    with pytest.raises(ValueError, match="Prohibited file-system access function"):
        SpreadsheetService.execute_safe_query(
            actor=test_actor,
            workspace_id=ws_id,
            table_name="telemetry",
            df=sample_telemetry_df,
            sql_query="SELECT * FROM read_csv('/etc/passwd')",
        )


def test_query_pagination_and_truncation_metadata(test_actor):
    # Create large dataframe
    df_large = pd.DataFrame({
        "id": list(range(1200)),
        "val": [i * 0.5 for i in range(1200)],
    })

    res = SpreadsheetService.execute_safe_query(
        actor=test_actor,
        workspace_id="ws_page_test",
        table_name="large_data",
        df=df_large,
        sql_query="SELECT * FROM large_data",
        page=1,
        page_size=500,
    )

    assert res["total_matching_rows"] == 1200
    assert res["row_count"] == 500
    assert res["truncated"] is True
    assert res["page"] == 1


def test_deterministic_engineering_calculations(test_actor):
    ws_id = "ws_calc_test"

    # 1. Reynolds Number Calculation
    re_res = SpreadsheetService.calculate_metric(
        actor=test_actor,
        workspace_id=ws_id,
        operation="reynolds_number",
        inputs={
            "density": 850.0,       # kg/m3 (oil)
            "velocity": 2.4,        # m/s
            "diameter": 0.15,       # m (150 mm pipe)
            "viscosity": 0.003,     # Pa.s
        },
    )
    assert isinstance(re_res, CalculationResult)
    assert re_res.operation == "reynolds_number"
    assert re_res.result_si == 102000.0  # (850 * 2.4 * 0.15) / 0.003
    assert len(re_res.steps) == 2
    assert len(re_res.result_hash) == 64

    # 2. Vibration RMS Calculation
    vib_res = SpreadsheetService.calculate_metric(
        actor=test_actor,
        workspace_id=ws_id,
        operation="vibration_rms",
        inputs={"vibration_peak": 8.0},  # mm/s
    )
    assert round(vib_res.result_display, 2) == 5.66  # 8.0 / sqrt(2)
    assert vib_res.display_unit == "mm/s RMS"

    # 3. Pump Head Calculation
    head_res = SpreadsheetService.calculate_metric(
        actor=test_actor,
        workspace_id=ws_id,
        operation="pump_head",
        inputs={
            "discharge_pressure_pa": 850000.0,
            "suction_pressure_pa": 150000.0,
            "fluid_density": 850.0,
        },
    )
    assert head_res.display_unit == "m"
    assert head_res.result_si > 0.0
