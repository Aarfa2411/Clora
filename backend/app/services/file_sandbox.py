"""
Production-Hardened Local File Sandbox for Clora (INDUSAI-X).
Enforces strict workspace directory boundaries, OS-level traversal defense,
symlink/junction rejection, hard-link write isolation, Windows device/ADS protection,
Unicode NFC normalization, and atomic TOCTOU-resistant file operations.
"""

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from backend.app.core.config import settings
from backend.app.core.tool_authorization import (
    ActorContext,
    AuthorizationDecision,
    ResourceContext,
    ToolAuthorizationGateway,
)
from backend.app.services import audit_service


class SandboxSecurityError(Exception):
    """Raised when an operation violates sandbox boundaries or security policies."""
    pass


class PathSecurityGuard:
    """
    OS-level and canonical boundary enforcement engine.
    Protects against traversal, symlink hijacking, Windows ADS, DOS devices, and case collisions.
    """

    DOS_DEVICE_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }

    @classmethod
    def get_sandbox_root(cls, workspace_id: str) -> Path:
        """Computes and initializes the canonical sandbox root for a workspace."""
        storage_base = getattr(settings, "STORAGE_DIR", getattr(settings, "STORAGE_PATH", "storage"))
        base = Path(storage_base) / "workspaces" / workspace_id / "sandbox"
        base.mkdir(parents=True, exist_ok=True)
        # Ensure standard partition subdirectories exist
        for sub in ["input", "working", "output", "temp"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base.resolve()

    @classmethod
    def validate_and_resolve_path(
        cls,
        workspace_id: str,
        subfolder: str,
        rel_path: str,
        must_exist: bool = False,
    ) -> Path:
        """
        Validates, canonicalizes, and bounds a path strictly within the workspace sandbox.
        """
        if not rel_path or not rel_path.strip():
            raise SandboxSecurityError("Relative path cannot be empty.")

        # 1. Unicode NFC Normalization
        norm_path_str = unicodedata.normalize("NFC", rel_path.strip().replace("\\", "/"))

        # 2. Check for Windows Alternate Data Streams (colon after drive prefix or in filename)
        # Colons in filenames indicate ADS on NTFS (e.g. file.txt:hidden)
        if ":" in norm_path_str:
            raise SandboxSecurityError("Alternate Data Streams (ADS) are strictly prohibited.")

        # 3. Check for Windows DOS Device Names
        parts = [p.strip() for p in norm_path_str.split("/") if p.strip()]
        for part in parts:
            stem = part.split(".")[0].upper()
            if stem in cls.DOS_DEVICE_NAMES:
                raise SandboxSecurityError(f"Access to Windows device name '{part}' is strictly prohibited.")

        # 4. Resolve sandbox root and target path
        sandbox_root = cls.get_sandbox_root(workspace_id)
        valid_subfolders = {"input", "working", "output", "temp"}
        if subfolder not in valid_subfolders:
            raise SandboxSecurityError(f"Invalid sandbox subfolder '{subfolder}'. Must be one of {valid_subfolders}.")

        folder_root = (sandbox_root / subfolder).resolve()
        target = (folder_root / norm_path_str).resolve()

        # 5. Strict Sandbox Boundary Check
        try:
            target.relative_to(folder_root)
        except ValueError:
            raise SandboxSecurityError(f"Path traversal detected: path resolves outside sandbox '{subfolder}/' directory.")

        # 6. Symlink & Windows Junction Inspection
        # Walk from folder_root to target verifying no components are symlinks / reparse points
        current = folder_root
        for part in target.relative_to(folder_root).parts:
            current = current / part
            if current.exists() and (os.path.islink(str(current)) or current.is_symlink()):
                raise SandboxSecurityError(f"Symlinks and junctions are prohibited inside sandbox: {part}")

        if must_exist and not target.exists():
            raise FileNotFoundError(f"Requested file does not exist: {rel_path}")

        return target


class WorkspaceFileSandbox:
    """
    Sandboxed file operations engine for local workspaces.
    Integrates ABAC authorization, cryptographic audit logging, and TOCTOU resistance.
    """

    MAX_READ_BYTES = 10 * 1024 * 1024  # 10 MB limit for single reads
    MAX_WRITE_BYTES = 50 * 1024 * 1024  # 50 MB limit for writes

    @classmethod
    def read_file(
        cls,
        actor: ActorContext,
        workspace_id: str,
        subfolder: Literal["input", "working", "output", "temp"],
        rel_path: str,
        max_bytes: int = MAX_READ_BYTES,
    ) -> Dict[str, Any]:
        """Reads file content safely within the sandbox."""
        resource = ResourceContext(workspace_id=workspace_id, subfolder=subfolder, rel_path=rel_path)
        decision = ToolAuthorizationGateway.evaluate(actor, "file:read", resource)
        if not decision.allowed:
            raise SandboxSecurityError(f"Access Denied: {decision.reason}")

        target_path = PathSecurityGuard.validate_and_resolve_path(
            workspace_id=workspace_id, subfolder=subfolder, rel_path=rel_path, must_exist=True
        )

        if not target_path.is_file():
            raise SandboxSecurityError(f"Path is not a regular file: {rel_path}")

        size = target_path.stat().st_size
        if size > max_bytes:
            raise SandboxSecurityError(f"File size ({size} bytes) exceeds maximum read limit ({max_bytes} bytes).")

        content = target_path.read_text(encoding="utf-8", errors="ignore")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Audit event record (hash-only)
        audit_service.log_action(
            db=None,  # Handled in caller context or standalone
            action="FILE_READ",
            resource=f"sandbox:{workspace_id}:{subfolder}/{rel_path}",
            user_id=actor.actor_id,
            workspace_id=workspace_id,
            details={
                "actor_type": actor.actor_type,
                "role": actor.role,
                "content_sha256": content_hash,
                "size_bytes": size,
                "policy_id": decision.policy_id,
            },
        )

        return {
            "workspace_id": workspace_id,
            "subfolder": subfolder,
            "rel_path": rel_path,
            "size_bytes": size,
            "content_sha256": content_hash,
            "content": content,
        }

    @classmethod
    def write_file(
        cls,
        actor: ActorContext,
        workspace_id: str,
        subfolder: Literal["working", "output", "temp"],
        rel_path: str,
        content: str,
        is_critical_procedure: bool = False,
    ) -> Dict[str, Any]:
        """
        Writes data atomically to the sandbox with hard-link isolation and TOCTOU defense.
        """
        resource = ResourceContext(
            workspace_id=workspace_id,
            subfolder=subfolder,
            rel_path=rel_path,
            is_critical_procedure=is_critical_procedure,
        )
        decision = ToolAuthorizationGateway.evaluate(actor, "file:write", resource)
        if not decision.allowed:
            raise SandboxSecurityError(f"Access Denied: {decision.reason}")

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > cls.MAX_WRITE_BYTES:
            raise SandboxSecurityError(f"Payload size ({len(content_bytes)} bytes) exceeds max limit ({cls.MAX_WRITE_BYTES} bytes).")

        target_path = PathSecurityGuard.validate_and_resolve_path(
            workspace_id=workspace_id, subfolder=subfolder, rel_path=rel_path, must_exist=False
        )

        # Hard-Link Detection & Write Isolation (if file exists with nlink > 1, unlink to prevent shared inode overwrite)
        if target_path.exists():
            st = target_path.stat()
            if hasattr(st, "st_nlink") and st.st_nlink > 1:
                target_path.unlink()  # Break hard-link association

        # Atomic write pattern using sibling temporary file + replace
        parent_dir = target_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        temp_path = parent_dir / f".tmp_{os.urandom(8).hex()}_{target_path.name}"

        try:
            with open(temp_path, "wb") as f:
                f.write(content_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename / replace
            os.replace(str(temp_path), str(target_path))
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

        content_hash = hashlib.sha256(content_bytes).hexdigest()

        audit_service.log_action(
            db=None,
            action="FILE_WRITE",
            resource=f"sandbox:{workspace_id}:{subfolder}/{rel_path}",
            user_id=actor.actor_id,
            workspace_id=workspace_id,
            details={
                "actor_type": actor.actor_type,
                "role": actor.role,
                "content_sha256": content_hash,
                "size_bytes": len(content_bytes),
                "policy_id": decision.policy_id,
            },
        )

        return {
            "workspace_id": workspace_id,
            "subfolder": subfolder,
            "rel_path": rel_path,
            "size_bytes": len(content_bytes),
            "content_sha256": content_hash,
            "status": "SUCCESS",
        }

    @classmethod
    def list_files(
        cls,
        actor: ActorContext,
        workspace_id: str,
        subfolder: Literal["input", "working", "output", "temp", "any"] = "any",
        recursive: bool = True,
    ) -> List[Dict[str, Any]]:
        """Lists files in workspace sandbox partitions with metadata."""
        resource = ResourceContext(workspace_id=workspace_id, subfolder=subfolder if subfolder != "any" else "working")
        decision = ToolAuthorizationGateway.evaluate(actor, "file:list", resource)
        if not decision.allowed:
            raise SandboxSecurityError(f"Access Denied: {decision.reason}")

        sandbox_root = PathSecurityGuard.get_sandbox_root(workspace_id)
        search_dirs = [sandbox_root / subfolder] if subfolder != "any" else [sandbox_root / s for s in ["input", "working", "output", "temp"]]

        results = []
        for s_dir in search_dirs:
            if not s_dir.exists():
                continue
            sub_name = s_dir.name
            pattern = "**/*" if recursive else "*"
            for p in s_dir.glob(pattern):
                if p.is_file() and not p.name.startswith(".tmp_"):
                    try:
                        st = p.stat()
                        results.append({
                            "subfolder": sub_name,
                            "rel_path": str(p.relative_to(s_dir)).replace("\\", "/"),
                            "size_bytes": st.st_size,
                            "modified_at": st.st_mtime,
                        })
                    except Exception:
                        pass
        return results

    @classmethod
    def search_files(
        cls,
        actor: ActorContext,
        workspace_id: str,
        query: str,
        subfolder: Literal["input", "working", "output", "temp", "any"] = "any",
        regex: bool = False,
    ) -> Dict[str, Any]:
        """Grep/search across sandboxed text files with forensic manifest tracking."""
        resource = ResourceContext(workspace_id=workspace_id, subfolder=subfolder if subfolder != "any" else "working")
        decision = ToolAuthorizationGateway.evaluate(actor, "file:search", resource)
        if not decision.allowed:
            raise SandboxSecurityError(f"Access Denied: {decision.reason}")

        files = cls.list_files(actor, workspace_id, subfolder, recursive=True)
        matches = []
        manifest_entries = []

        compiled_re = re.compile(query, re.IGNORECASE) if regex else None

        for f in files:
            p = PathSecurityGuard.validate_and_resolve_path(
                workspace_id, f["subfolder"], f["rel_path"], must_exist=True
            )
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                manifest_entries.append({
                    "subfolder": f["subfolder"],
                    "path": f["rel_path"],
                    "hash": file_hash,
                })

                lines = text.splitlines()
                for line_idx, line in enumerate(lines, 1):
                    is_match = compiled_re.search(line) if regex else (query.lower() in line.lower())
                    if is_match:
                        matches.append({
                            "subfolder": f["subfolder"],
                            "file": f["rel_path"],
                            "line": line_idx,
                            "snippet": line.strip()[:200],
                        })
            except Exception:
                continue

        manifest_hash = hashlib.sha256(str(manifest_entries).encode("utf-8")).hexdigest()

        # Deterministic bulk scan audit entry
        audit_service.log_action(
            db=None,
            action="BULK_FILE_SCAN",
            resource=f"sandbox:{workspace_id}:{subfolder}",
            user_id=actor.actor_id,
            workspace_id=workspace_id,
            details={
                "files_scanned": len(files),
                "matches_found": len(matches),
                "manifest_hash": manifest_hash,
                "policy_id": decision.policy_id,
            },
        )

        return {
            "workspace_id": workspace_id,
            "query": query,
            "files_scanned": len(files),
            "matches_count": len(matches),
            "manifest_hash": manifest_hash,
            "matches": matches[:500],  # Cap output to prevent payload bloat
        }
