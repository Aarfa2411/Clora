"""
Advisory AST Security Guard for INDUSAI-X Sandbox.
Provides rapid syntax validation, helpful developer diagnostics, and advisory safety checks
prior to container sandbox execution.
"""

import ast
from typing import List, Optional, Set

from pydantic import BaseModel, Field


class ASTCheckResult(BaseModel):
    valid: bool
    syntax_ok: bool = True
    issues: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


# Explicitly blocked modules
BLOCKED_MODULES: Set[str] = {
    # Network / exfiltration
    "socket", "urllib", "requests", "http", "ftplib", "telnetlib", "smtplib",
    "aiohttp", "httpx", "paramiko",
    # Subprocess / execution / reflection
    "subprocess", "pty", "multiprocessing", "importlib", "ctypes", "inspect",
    "posix", "nt", "signal", "shutil", "builtins",
    # Database drivers (enforce single path via Member 6 TabularEngine)
    "duckdb", "sqlite3", "psycopg2", "mysql", "sqlalchemy",
}

# Blocked call attributes on 'os' module
BLOCKED_OS_ATTRIBUTES: Set[str] = {
    "system", "popen", "spawn", "spawnp", "spawnl", "execv", "execve",
    "execl", "execlp", "kill", "chmod", "chown", "remove", "unlink", "rmdir"
}

# Blocked built-in function names
BLOCKED_BUILTINS: Set[str] = {
    "eval", "exec", "__import__", "compile", "breakpoint", "getattr", "setattr", "delattr", "globals", "locals"
}

# Blocked introspection / reflection attributes used in sandbox escape exploits
BLOCKED_INTROSPECTION_ATTRIBUTES: Set[str] = {
    "__subclasses__", "__builtins__", "__globals__", "__class__", "__base__",
    "__bases__", "__import__", "__code__", "__reduce__", "__mro__"
}


class ASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.issues: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in BLOCKED_MODULES:
                if base_mod == "duckdb":
                    self.issues.append(
                        "Direct 'duckdb' import is prohibited. Use pre-extracted telemetry data "
                        "at '/workspace/input/telemetry.csv' or Member 6 TabularEngine."
                    )
                else:
                    self.issues.append(f"Blocked module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in BLOCKED_MODULES:
                if base_mod == "duckdb":
                    self.issues.append(
                        "Direct 'duckdb' import is prohibited. Use pre-extracted telemetry data "
                        "at '/workspace/input/telemetry.csv' or Member 6 TabularEngine."
                    )
                else:
                    self.issues.append(f"Blocked module import: '{node.module}'")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in ("__builtins__", "__loader__", "__spec__"):
            self.issues.append(f"Direct access to '{node.id}' is prohibited.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in BLOCKED_INTROSPECTION_ATTRIBUTES:
            self.issues.append(f"Prohibited introspection attribute: '{node.attr}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct builtin calls (eval, exec, __import__, getattr, globals)
        if isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_BUILTINS:
                self.issues.append(f"Disallowed call to built-in function: '{node.func.id}'")

        # Check os.<blocked_call>
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if node.func.attr in BLOCKED_OS_ATTRIBUTES:
                    self.issues.append(f"Prohibited OS operation: 'os.{node.func.attr}'")

        self.generic_visit(node)


class ASTSecurityGuard:
    """Pre-flight AST inspection providing fast syntax errors and security feedback."""

    def check(self, code: str) -> ASTCheckResult:
        # 1. Syntax Check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ASTCheckResult(
                valid=False,
                syntax_ok=False,
                issues=[f"SyntaxError on line {e.lineno}: {e.msg}"],
                error_message=f"SyntaxError on line {e.lineno}: {e.msg}",
            )
        except Exception as e:
            return ASTCheckResult(
                valid=False,
                syntax_ok=False,
                issues=[f"Parse error: {str(e)}"],
                error_message=f"Parse error: {str(e)}",
            )

        # 2. Advisory Security Inspection
        visitor = ASTVisitor()
        visitor.visit(tree)

        if visitor.issues:
            return ASTCheckResult(
                valid=False,
                syntax_ok=True,
                issues=visitor.issues,
                error_message="; ".join(visitor.issues),
            )

        return ASTCheckResult(valid=True, syntax_ok=True, issues=[])


default_ast_guard = ASTSecurityGuard()
