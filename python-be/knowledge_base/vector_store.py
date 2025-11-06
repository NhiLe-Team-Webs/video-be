"""
Embedding encoder and in-memory vector similarity search utilities.

This module provides tools for converting text into numerical vector embeddings
and performing efficient similarity searches on these embeddings in memory.
It is a core component for the knowledge retrieval system, enabling semantic
search capabilities within the knowledge base.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

import math  # Standard math functions (though not directly used in final code, often useful for vector ops)
from dataclasses import dataclass  # For creating simple data-holding classes
from typing import Iterable, List, Sequence  # Type hinting utilities

import numpy as np  # Numerical computing library, essential for vector operations

try:
    from sentence_transformers import SentenceTransformer  # Attempt to import SentenceTransformer
except ImportError:
    # Fallback if SentenceTransformer is not installed, allowing the system to run
    # with a simpler vectorization method.
    SentenceTransformer = None  # type: ignore[assignment]


@dataclass
class VectorSearchResult:
    """
    Represents a single result from a vector similarity search.

    Attributes:
        chunk_id: The unique identifier of the knowledge chunk.
        score: The similarity score (e.g., cosine similarity) between the query
               and the chunk's vector. Higher scores indicate greater similarity.
        text: The original text content of the chunk.
        metadata: A dictionary containing additional metadata about the chunk.
    """
    chunk_id: str
    score: float
    text: str
    metadata: dict


class Vectoriser:
    """
    Encodes text into dense numerical vectors (embeddings).

    This class primarily uses a pre-trained SentenceTransformer model for high-quality
    semantic embeddings. If SentenceTransformer is not available or fails to load,
    it falls back to a simpler TF-IDF-like hashing method for basic vectorization.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        """
        Initializes the Vectoriser.

        Args:
            model_name: The name of the SentenceTransformer model to load.
                        Defaults to "sentence-transformers/all-MiniLM-L6-v2".
        """
        self.model_name = model_name
        self._model = None  # Internal cache for the loaded SentenceTransformer model

    @property
    def model(self) -> SentenceTransformer | None:
        """
        Lazily loads the SentenceTransformer model.

        The model is loaded only once upon first access. If loading fails (e.g.,
        model not found, no internet), it sets `_model` to None and subsequent
        calls will use the fallback `encode` method.

        Returns:
            An instance of `SentenceTransformer` if successfully loaded, otherwise `None`.
        """
        if self._model is None and SentenceTransformer is not None:
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception:
                # Log the error if model loading fails in a real application
                self._model = None
        return self._model

    def encode(self, text: str) -> List[float]:
        """
        Encodes a given text string into a dense vector embedding.

        Prioritizes using the SentenceTransformer model. If the model is not
        available, it uses a simple hashing-based fallback. Embeddings are
        normalized to unit length.

        Args:
            text: The input text string to encode.

        Returns:
            A list of floats representing the normalized vector embedding of the text.
        """
        if self.model is not None:
            # Encode using SentenceTransformer and normalize embeddings
            vector = self.model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        
        # Simple hashing fallback if SentenceTransformer is not available
        tokens = text.lower().split()
        vec = np.zeros(512, dtype=np.float32)  # Fixed-size vector for hashing
        for token in tokens:
            idx = hash(token) % 512  # Map token to an index
            vec[idx] += 1  # Increment count for that index
        
        norm = np.linalg.norm(vec)  # Calculate L2 norm for normalization
        if norm == 0:
            return vec.tolist()  # Return as is if vector is all zeros
        return (vec / norm).tolist()  # Normalize to unit vector


class InMemoryVectorStore:
    """
    An in-memory store for vector embeddings, enabling fast similarity searches.

    This store holds a collection of vectors and their associated metadata,
    allowing for efficient retrieval of similar vectors based on cosine similarity.
    """

    def __init__(self) -> None:
        """
        Initializes an empty InMemoryVectorStore.
        """
        self._vectors: List[np.ndarray] = []  # Stores the numerical vectors
        self._payload: List[dict] = []        # Stores the metadata associated with each vector

    def add(self, vector: Sequence[float], metadata: dict) -> None:
        """
        Adds a single vector and its metadata to the store.

        Args:
            vector: A sequence of floats representing the vector embedding.
            metadata: A dictionary containing metadata associated with the vector.
        """
        self._vectors.append(np.array(vector, dtype=np.float32))
        self._payload.append(metadata)

    def extend(self, vectors: Iterable[Sequence[float]], metadatas: Iterable[dict]) -> None:
        """
        Adds multiple vectors and their corresponding metadatas to the store.

        Args:
            vectors: An iterable of vector embeddings.
            metadatas: An iterable of metadata dictionaries, corresponding to `vectors`.
        """
        for vector, metadata in zip(vectors, metadatas):
            self.add(vector, metadata)

    def search(self, query_vector: Sequence[float], top_k: int = 5) -> List[VectorSearchResult]:
        """
        Performs a cosine similarity search against all stored vectors.

        Args:
            query_vector: The vector representation of the query.
            top_k: The number of top similar results to return.

        Returns:
            A list of `VectorSearchResult` objects, sorted by similarity score
            in descending order. Returns an empty list if no vectors are stored
            or if the query vector is zero.
        """
        if not self._vectors:
            return []  # No vectors to search against
        
        query = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []  # Cannot compute similarity with a zero query vector
        
        scores: List[VectorSearchResult] = []
        for vector, metadata in zip(self._vectors, self._payload):
            denom = np.linalg.norm(vector) * query_norm
            if denom == 0:
                continue  # Skip if either vector is zero (cannot normalize)
            
            # Calculate cosine similarity
            score = float(np.dot(vector, query) / denom)
            scores.append(
                VectorSearchResult(
                    chunk_id=metadata.get("chunk_id", ""),
                    score=score,
                    text=metadata.get("text", ""),
                    metadata=metadata,
                )
            )
        
        scores.sort(key=lambda item: item.score, reverse=True)  # Sort by score in descending order
        return scores[:top_k]  # Return the top_k results
