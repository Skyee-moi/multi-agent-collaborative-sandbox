import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# On cloud (Render free tier), use /tmp which is always writable
_IS_CLOUD = os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT")

class FallbackVectorStore:
    """Fallback vector store if ChromaDB native bindings are initializing."""
    def __init__(self):
        self.memories: List[Dict[str, Any]] = []

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        self.memories.append({
            "text": text,
            "metadata": metadata or {}
        })

    def search_memory(self, query: str, limit: int = 3) -> List[str]:
        query_words = set(query.lower().split())
        scored = []
        for mem in self.memories:
            text = mem["text"]
            text_words = set(text.lower().split())
            overlap = len(query_words.intersection(text_words))
            if overlap > 0:
                scored.append((overlap, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

class ChromaMemoryStore:
    """Long-term memory & semantic RAG manager backed by ChromaDB."""
    def __init__(self, persist_dir: Optional[str] = None):
        if not persist_dir:
            if _IS_CLOUD:
                persist_dir = "/tmp/chroma_db"
            else:
                base = Path(__file__).resolve().parent.parent.parent
                persist_dir = str(base / "chroma_db")
        
        self.persist_dir = persist_dir
        self.store = None
        self.is_chroma = False

        try:
            import chromadb
            from chromadb.config import Settings
            
            os.makedirs(self.persist_dir, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection("macs_longterm_memory")
            self.is_chroma = True
            print(f"[Memory] ChromaDB store initialized at '{self.persist_dir}'")
        except Exception as e:
            print(f"[Memory] ChromaDB notice ({e}). Using lightweight vector store fallback.")
            self.store = FallbackVectorStore()

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None, doc_id: Optional[str] = None):
        if not text or not text.strip():
            return
        
        metadata = metadata or {"source": "user_session"}
        
        if self.is_chroma:
            try:
                import uuid
                uid = doc_id or str(uuid.uuid4())
                self.collection.add(
                    documents=[text],
                    metadatas=[metadata],
                    ids=[uid]
                )
            except Exception as e:
                print(f"[ChromaDB Error] add_memory failed: {e}")
        else:
            self.store.add_memory(text, metadata)

    def search_memory(self, query: str, limit: int = 3) -> List[str]:
        if not query or not query.strip():
            return []
            
        if self.is_chroma:
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit
                )
                docs = results.get("documents", [[]])[0]
                return docs if docs else []
            except Exception as e:
                print(f"[ChromaDB Error] search_memory failed: {e}")
                return []
        else:
            return self.store.search_memory(query, limit)
