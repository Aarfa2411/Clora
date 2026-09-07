"""
INDUSAI-X: Sovereign On-Premise Agentic AI Workbench for MRPL (SIH26117)
Intelligence Backbone Package.
"""

from indusai.config import settings

try:
    from indusai.agents.graph import IndusAIGraph
except ImportError:
    IndusAIGraph = None  # type: ignore

try:
    from indusai.storage.vector_store import ChromaVectorStore
except ImportError:
    ChromaVectorStore = None  # type: ignore

try:
    from indusai.ingestion.schema import ChunkMetadata, Chunk, IngestedDocument
    from indusai.ingestion.chunker import IntelligentChunker
    from indusai.ingestion.document_parser import DocumentParser
except ImportError:
    ChunkMetadata = None  # type: ignore
    Chunk = None  # type: ignore
    IngestedDocument = None  # type: ignore
    IntelligentChunker = None  # type: ignore
    DocumentParser = None  # type: ignore

try:
    from indusai.verification.verifier import EvidenceVerifier
except ImportError:
    EvidenceVerifier = None  # type: ignore

try:
    from indusai.evaluation.metrics import Evaluator
except ImportError:
    Evaluator = None  # type: ignore

__version__ = "1.0.0"
__all__ = [
    "settings",
    "IndusAIGraph",
    "ChromaVectorStore",
    "ChunkMetadata",
    "Chunk",
    "IngestedDocument",
    "IntelligentChunker",
    "DocumentParser",
    "EvidenceVerifier",
    "Evaluator"
]

