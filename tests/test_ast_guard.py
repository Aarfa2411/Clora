"""
Unit tests for Advisory AST Security Guard.
"""

from backend.sandbox.ast_guard import ASTSecurityGuard


class TestASTSecurityGuard:
    def setup_method(self):
        self.guard = ASTSecurityGuard()

    def test_valid_analytical_code(self):
        code = (
            "import os.path\n"
            "import math\n"
            "import pandas as pd\n"
            "import numpy as np\n\n"
            "data = [1.2, 3.4, 5.6]\n"
            "mean_val = np.mean(data)\n"
            "print(f'Mean: {mean_val}')\n"
        )
        res = self.guard.check(code)
        assert res.valid is True
        assert res.syntax_ok is True
        assert len(res.issues) == 0

    def test_syntax_error_detection(self):
        code = "def broken_func(\n    print('missing paren'"
        res = self.guard.check(code)
        assert res.valid is False
        assert res.syntax_ok is False
        assert "SyntaxError" in res.error_message

    def test_blocks_network_libraries(self):
        for mod in ["socket", "urllib", "requests", "http.client", "aiohttp", "httpx"]:
            code = f"import {mod}\nprint('attempt')"
            res = self.guard.check(code)
            assert res.valid is False
            assert any(f"Blocked module import: '{mod}'" in issue for issue in res.issues)

    def test_blocks_process_execution(self):
        code = "import subprocess\nsubprocess.run(['ls'])"
        res = self.guard.check(code)
        assert res.valid is False
        assert any("subprocess" in issue for issue in res.issues)

    def test_blocks_os_system_calls(self):
        code = "import os\nos.system('whoami')"
        res = self.guard.check(code)
        assert res.valid is False
        assert any("os.system" in issue for issue in res.issues)

    def test_allows_os_path_safe_calls(self):
        code = "import os\npath = os.path.join('/workspace/input', 'test.csv')\nprint(path)"
        res = self.guard.check(code)
        assert res.valid is True

    def test_blocks_duckdb_single_path_enforcement(self):
        code = "import duckdb\nconn = duckdb.connect()"
        res = self.guard.check(code)
        assert res.valid is False
        assert "Direct 'duckdb' import is prohibited" in res.error_message

    def test_blocks_eval_exec_builtins(self):
        code = "eval('2 + 2')"
        res = self.guard.check(code)
        assert res.valid is False
        assert any("eval" in issue for issue in res.issues)

    def test_blocks_introspection_and_reflection_attributes(self):
        # Exploit payload attempting to traverse class hierarchy
        code = "subclasses = ().__class__.__base__.__subclasses__()"
        res = self.guard.check(code)
        assert res.valid is False
        assert any("Prohibited introspection attribute" in issue for issue in res.issues)

    def test_blocks_direct_builtins_access(self):
        code = "b = __builtins__\nprint(b)"
        res = self.guard.check(code)
        assert res.valid is False
        assert any("Direct access to '__builtins__'" in issue for issue in res.issues)

    def test_blocks_reflection_modules(self):
        for mod in ["importlib", "ctypes", "inspect", "shutil"]:
            code = f"import {mod}\nprint('attempt')"
            res = self.guard.check(code)
            assert res.valid is False
            assert any(f"Blocked module import: '{mod}'" in issue for issue in res.issues)
