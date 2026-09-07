"""
Unit tests for TabularEngine mathematical function execution and AST security.
Validates that POW, POWER, SQRT, and nested math functions pass the AST validator and execute.
"""

import pytest
import pandas as pd
from data_intelligence.tabular_engine import TabularEngine, SQLSecurityError


class TestTabularMath:
    def setup_method(self):
        self.engine = TabularEngine()
        df = pd.DataFrame({
            "val": [2.0, 4.0, 6.0, 8.0],
            "vibe": [1.5, 2.5, 3.5, 4.5],
        })
        self.engine.load_dataframe("test_tbl", df)

    def test_power_and_pow_functions(self):
        # Test POWER(val, 2)
        q1 = "SELECT POWER(val, 2) as val_sq FROM test_tbl"
        rows1, _ = self.engine.query(q1)
        assert len(rows1) == 4
        assert rows1[0]["val_sq"] == 4.0

        # Test POW(val, 2)
        q2 = "SELECT POW(val, 2) as val_sq FROM test_tbl"
        rows2, _ = self.engine.query(q2)
        assert len(rows2) == 4
        assert rows2[1]["val_sq"] == 16.0

    def test_nested_true_rms_calculation(self):
        # SQRT(AVG(POW(vibe, 2)))
        query = "SELECT SQRT(AVG(POW(vibe, 2))) as true_rms FROM test_tbl"
        rows, md = self.engine.query(query)
        assert len(rows) == 1
        assert rows[0]["true_rms"] > 0
        assert "true_rms" in md

    def test_forbidden_sql_functions_blocked(self):
        # Unapproved functions must still be blocked by AST validator
        with pytest.raises(SQLSecurityError):
            self.engine.query("SELECT read_csv('secret.csv') FROM test_tbl")

        with pytest.raises(SQLSecurityError):
            self.engine.query("SELECT version() FROM test_tbl")
