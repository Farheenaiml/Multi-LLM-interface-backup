import os
import logging
from typing import List, Dict, Any

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, persist_directory: str = "chroma_db", collection_name: str = "private_documents"):
        """
        Initializes ChromaDB persistent client and SentenceTransformer model.
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        # Initialize locally-running SentenceTransformer model
        logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2'...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Initialize ChromaDB
        os.makedirs(self.persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # Get or create our collection
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        logger.info(f"Initialized ChromaDB collection: {self.collection_name}")

    def add_documents(self, chunks: List[str], metadata: Dict[str, Any]):
        """
        Embed and insert document chunks into the VectorDB.
        """
        if not chunks:
            return

        # Generate a unique base ID for this document
        # Chroma expects unique IDs for every single chunk
        import uuid
        base_id = str(uuid.uuid4())
        
        ids = [f"{base_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [metadata for _ in range(len(chunks))]
        
        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        embeddings = self.embedding_model.encode(chunks, show_progress_bar=False).tolist()
        
        # Add to Chroma
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks
        )
        logger.info(f"Successfully added {len(chunks)} chunks to vector store.")

    def search_similar(self, query: str, top_k: int = 4) -> List[str]:
        """
        Search the collection for the closest matching chunks.
        """
        # Embed the query
        query_embedding = self.embedding_model.encode([query], show_progress_bar=False).tolist()
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k
        )
        
        # documents is a list of lists of strings
        docs = results.get("documents", [[]])
        
        if docs and len(docs) > 0:
            return docs[0]
        return []
