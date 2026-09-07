"""
Agent Tools Definition & Invocation Layer for Clora (INDUSAI-X).
Wraps the Tool Authorization Gateway, File Sandbox, Vision/OCR Service, and Spreadsheet Engine
into standard tools executable by LangGraph agents with deterministic governance.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from backend.app.core.tool_authorization import ActorContext
from backend.app.services.file_sandbox import WorkspaceFileSandbox
from backend.app.services.spreadsheet_service import SpreadsheetService
from backend.app.services.vision_ocr_service import VisionOCRService


class AgentToolExecutor:
    """
    Standard Tool Execution Dispatcher for LangGraph Multi-Agent Orchestrator.
    Guarantees that all agent-requested actions pass through deterministic authorization and audit trails.
    """

    def __init__(self, default_agent_role: str = "agent_investigation"):
        self.default_agent_role = default_agent_role
        self.sandbox = WorkspaceFileSandbox()
        self.spreadsheet_svc = SpreadsheetService()
        self.vision_svc = VisionOCRService()

    def _build_actor(self, agent_role: Optional[str] = None, session_id: str = "agent_session") -> ActorContext:
        return ActorContext(
            actor_type="agent",
            actor_id=f"agent_{agent_role or self.default_agent_role}",
            role=agent_role or self.default_agent_role,
            department="operations",
            session_id=session_id,
        )

    def read_file(self, workspace_id: str, subfolder: str, rel_path: str, agent_role: Optional[str] = None) -> Dict[str, Any]:
        """Reads sandboxed file contents."""
        actor = self._build_actor(agent_role)
        return self.sandbox.read_file(
            actor=actor,
            workspace_id=workspace_id,
            subfolder=subfolder,  # type: ignore
            rel_path=rel_path,
        )

    def write_working_file(self, workspace_id: str, rel_path: str, content: str, agent_role: Optional[str] = None) -> Dict[str, Any]:
        """Writes intermediate analysis data to sandbox/working/."""
        actor = self._build_actor(agent_role or "agent_investigation")
        return self.sandbox.write_file(
            actor=actor,
            workspace_id=workspace_id,
            subfolder="working",
            rel_path=rel_path,
            content=content,
        )

    def search_workspace_files(self, workspace_id: str, query: str, subfolder: str = "any", agent_role: Optional[str] = None) -> Dict[str, Any]:
        """Searches files across sandbox folders."""
        actor = self._build_actor(agent_role)
        return self.sandbox.search_files(
            actor=actor,
            workspace_id=workspace_id,
            query=query,
            subfolder=subfolder,  # type: ignore
        )

    async def ingest_handwritten_note(self, image_bytes: bytes, workspace_id: str, filename: str) -> Dict[str, Any]:
        """Processes handwritten shift logs or P&ID notes into canonical structured evidence."""
        evidence = await self.vision_svc.extract_from_image(
            image_bytes=image_bytes,
            workspace_id=workspace_id,
            source_filename=filename,
        )
        return evidence.model_dump()

    def query_spreadsheet(self, workspace_id: str, file_path: str, sql_query: str, page: int = 1, page_size: int = 100, agent_role: Optional[str] = None) -> Dict[str, Any]:
        """Executes safe SQL queries on tabular files."""
        actor = self._build_actor(agent_role or "agent_investigation")
        df, meta = self.spreadsheet_svc.load_sheet_as_dataframe(file_path)
        table_name = "dataset"
        res = self.spreadsheet_svc.execute_safe_query(
            actor=actor,
            workspace_id=workspace_id,
            table_name=table_name,
            df=df,
            sql_query=sql_query,
            page=page,
            page_size=page_size,
        )
        res["source_metadata"] = meta
        return res

    def calculate_engineering_metric(
        self,
        workspace_id: str,
        operation: Literal["reynolds_number", "vibration_rms", "pump_head", "heat_exchanger_lmtd", "thermal_efficiency"],
        inputs: Dict[str, float],
        source_evidence_ids: Optional[List[str]] = None,
        agent_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes deterministic engineering calculations."""
        actor = self._build_actor(agent_role or "agent_engineering")
        res = self.spreadsheet_svc.calculate_metric(
            actor=actor,
            workspace_id=workspace_id,
            operation=operation,
            inputs=inputs,
            source_evidence_ids=source_evidence_ids,
        )
        return res.model_dump()


agent_tools = AgentToolExecutor()
