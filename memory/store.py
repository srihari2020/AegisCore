import hashlib
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

class AegisMemory:
    def __init__(self, db_path: str = "./chroma_data"):
        self.embed_fn = OllamaEmbeddingFunction(
            url="http://127.0.0.1:11434/api/embeddings",
            model_name="nomic-embed-text",
        )
        self.client = chromadb.PersistentClient(path=db_path)
        self.memories = self.client.get_or_create_collection("episodic_memory", embedding_function=self.embed_fn)
        self.skills = self.client.get_or_create_collection("learned_skills", embedding_function=self.embed_fn)

    def add_memory(self, fact: str, category: str = "preference"):
        doc_id = hashlib.sha256(fact.encode()).hexdigest()[:16]
        self.memories.upsert(ids=[doc_id], documents=[fact], metadatas=[{"category": category}])

    def recall_memories(self, query: str, k: int = 5) -> list[str]:
        if self.memories.count() == 0:
            return []
        res = self.memories.query(query_texts=[query], n_results=min(k, self.memories.count()))
        return res["documents"][0] if res["documents"] else []

    def save_skill(self, skill_name: str, trigger_phrase: str, steps: list[str]):
        payload = f"{skill_name} | Trigger: {trigger_phrase} | Steps: {steps}"
        self.skills.upsert(ids=[skill_name], documents=[payload], metadatas=[{"skill_name": skill_name}])

    def recall_skills(self, query: str, k: int = 2) -> list[str]:
        if self.skills.count() == 0:
            return []
        res = self.skills.query(query_texts=[query], n_results=min(k, self.skills.count()))
        return res["documents"][0] if res["documents"] else []
