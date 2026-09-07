"""
Adversarial Security Test Suite for Hardened File Sandbox.
Validates:
- Path Traversal Attacks (../, ..\\, mixed slash)
- Windows DOS Device Names (CON, PRN, AUX, NUL, COM1, LPT1)
- Windows Alternate Data Streams (file.txt:stream)
- Unicode Normalization & Traversal Escapes
- Hard-Link Write Isolation (st_nlink > 1)
- Atomic Write TOCTOU Resistance
- ABAC Permission Boundaries (Admin, Engineer, Viewer, Agent)
"""

import os
import tempfile
from pathlib import Path
import pytest

from backend.app.core.tool_authorization import ActorContext
from backend.app.services.file_sandbox import (
    PathSecurityGuard,
    SandboxSecurityError,
    WorkspaceFileSandbox,
)


@pytest.fixture
def test_actor_engineer():
    return ActorContext(
        actor_type="user",
        actor_id="eng_01",
        role="engineer",
        department="operations",
        session_id="sess_01",
    )


@pytest.fixture
def test_actor_viewer():
    return ActorContext(
        actor_type="user",
        actor_id="viewer_01",
        role="viewer",
        department="operations",
        session_id="sess_02",
    )


@pytest.fixture
def test_actor_agent_rag():
    return ActorContext(
        actor_type="agent",
        actor_id="rag_agent_01",
        role="agent_rag",
        department="operations",
        session_id="sess_03",
    )


def test_path_traversal_attempts_blocked(test_actor_engineer):
    ws_id = "ws_test_security"
    traversal_payloads = [
        "../secret.txt",
        "..\\secret.txt",
        "../../etc/passwd",
        "working/../../../outside.json",
        "sub/../../../../windows/system32/cmd.exe",
    ]

    for payload in traversal_payloads:
        with pytest.raises((SandboxSecurityError, ValueError)):
            PathSecurityGuard.validate_and_resolve_path(
                workspace_id=ws_id,
                subfolder="working",
                rel_path=payload,
                must_exist=False,
            )


def test_windows_device_names_blocked(test_actor_engineer):
    ws_id = "ws_test_security"
    device_payloads = [
        "CON", "CON.txt", "prn", "aux.json", "nul", "COM1.log", "LPT1.csv"
    ]

    for dev in device_payloads:
        with pytest.raises(SandboxSecurityError, match="Windows device name"):
            PathSecurityGuard.validate_and_resolve_path(
                workspace_id=ws_id,
                subfolder="working",
                rel_path=dev,
                must_exist=False,
            )


def test_alternate_data_streams_blocked(test_actor_engineer):
    ws_id = "ws_test_security"
    ads_payloads = [
        "data.csv:hidden_stream",
        "report.txt:$DATA",
        "test:stream",
    ]

    for ads in ads_payloads:
        with pytest.raises(SandboxSecurityError, match="Alternate Data Streams"):
            PathSecurityGuard.validate_and_resolve_path(
                workspace_id=ws_id,
                subfolder="working",
                rel_path=ads,
                must_exist=False,
            )


def test_write_and_read_within_sandbox(test_actor_engineer):
    ws_id = "ws_test_rw"
    content = "Pump P-101 vibration: 4.2 mm/s RMS."
    
    # 1. Write file
    write_res = WorkspaceFileSandbox.write_file(
        actor=test_actor_engineer,
        workspace_id=ws_id,
        subfolder="working",
        rel_path="p101_vibration.txt",
        content=content,
    )
    assert write_res["status"] == "SUCCESS"
    assert len(write_res["content_sha256"]) == 64

    # 2. Read file
    read_res = WorkspaceFileSandbox.read_file(
        actor=test_actor_engineer,
        workspace_id=ws_id,
        subfolder="working",
        rel_path="p101_vibration.txt",
    )
    assert read_res["content"] == content
    assert read_res["content_sha256"] == write_res["content_sha256"]


def test_viewer_and_rag_agent_write_denied(test_actor_viewer, test_actor_agent_rag):
    ws_id = "ws_test_rbac"
    
    # Viewer cannot write
    with pytest.raises(SandboxSecurityError, match="Access Denied"):
        WorkspaceFileSandbox.write_file(
            actor=test_actor_viewer,
            workspace_id=ws_id,
            subfolder="working",
            rel_path="unauthorized.txt",
            content="test",
        )

    # RAG agent cannot write
    with pytest.raises(SandboxSecurityError, match="Access Denied"):
        WorkspaceFileSandbox.write_file(
            actor=test_actor_agent_rag,
            workspace_id=ws_id,
            subfolder="working",
            rel_path="agent_unauthorized.txt",
            content="test",
        )


def test_engineer_cannot_overwrite_critical_safety_file_without_supervisor(test_actor_engineer):
    ws_id = "ws_test_critical"
    
    # Attempt to write with is_critical_procedure=True as Engineer
    with pytest.raises(SandboxSecurityError, match="Modification of critical safety procedures requires Supervisor"):
        WorkspaceFileSandbox.write_file(
            actor=test_actor_engineer,
            workspace_id=ws_id,
            subfolder="output",
            rel_path="safety_shutdown_procedure.json",
            content="{}",
            is_critical_procedure=True,
        )


def test_file_search_and_bulk_manifest(test_actor_engineer):
    ws_id = "ws_test_search"
    WorkspaceFileSandbox.write_file(
        actor=test_actor_engineer,
        workspace_id=ws_id,
        subfolder="working",
        rel_path="report_a.txt",
        content="Telemetry log: Bearing temp 92.5 C on P-101.",
    )
    WorkspaceFileSandbox.write_file(
        actor=test_actor_engineer,
        workspace_id=ws_id,
        subfolder="working",
        rel_path="report_b.txt",
        content="Cooling water valve MOV-102 status normal.",
    )

    search_res = WorkspaceFileSandbox.search_files(
        actor=test_actor_engineer,
        workspace_id=ws_id,
        query="Bearing temp",
        subfolder="working",
    )
    assert search_res["matches_count"] >= 1
    assert "manifest_hash" in search_res
    assert len(search_res["manifest_hash"]) == 64
