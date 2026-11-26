import hashlib
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

class AegisMemory:
    def __init__(self, db_path: str = "./chroma_data"):
        # Uses local CPU ONNX MiniLM (~4ms per query, 0 VRAM, no Ollama model swap)
        self.embed_fn = DefaultEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=db_path)
        self.memories = self.client.get_or_create_collection(
            name="episodic_memory",
            embedding_function=self.embed_fn,
        )
        self.skills = self.client.get_or_create_collection(
            name="learned_skills",
            embedding_function=self.embed_fn,
        )

    def add_memory(self, fact: str, category: str = "preference") -> str:
        clean_fact = fact.strip()
        doc_id = hashlib.sha256(clean_fact.lower().encode()).hexdigest()[:16]
        self.memories.upsert(
            ids=[doc_id],
            documents=[clean_fact],
            metadatas=[{"category": category}],
        )
        return clean_fact

    def recall_memories(self, query: str, k: int = 5) -> list[str]:
        total = self.memories.count()
        if total == 0:
            return []
        res = self.memories.query(query_texts=[query], n_results=min(k, total))
        return res["documents"][0] if res["documents"] else []

    def save_skill(self, skill_name: str, trigger_phrase: str, steps: list[str]) -> str:
        payload = f"{skill_name} | Trigger: {trigger_phrase} | Steps: {' -> '.join(steps)}"
        self.skills.upsert(
            ids=[skill_name.strip().lower()],
            documents=[payload],
            metadatas=[{"skill_name": skill_name, "trigger": trigger_phrase}],
        )
        return payload

    def recall_skills(self, query: str, k: int = 3) -> list[str]:
        total = self.skills.count()
        if total == 0:
            return []
        res = self.skills.query(query_texts=[query], n_results=min(k, total))
        return res["documents"][0] if res["documents"] else []
