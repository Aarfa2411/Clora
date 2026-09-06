"""INDUSAI-X RAG Package"""

try:
    from backend.rag.chroma_store import ChromaEvidenceStore
except ImportError:
    ChromaEvidenceStore = None  # type: ignore

try:
    from backend.rag.embeddings import LocalEmbeddingService
except ImportError:
    LocalEmbeddingService = None  # type: ignore

from backend.rag.chunking import Chunk, ChunkMetadata, IntelligentChunker
from backend.rag.evidence import Evidence, EvidencePack
from backend.rag.ingestion import DocumentParser, IngestedDocument, ParsedSection
from backend.rag.retrieval import IndustrialQueryExpander, IndustrialReranker, PermissionFilter



__all__ = [
    "Evidence",
    "EvidencePack",
    "LocalEmbeddingService",
    "ChromaEvidenceStore",
    "DocumentParser",
    "IngestedDocument",
    "ParsedSection",
    "ChunkMetadata",
    "Chunk",
    "IntelligentChunker",
    "PermissionFilter",
    "IndustrialQueryExpander",
    "IndustrialReranker",
]
