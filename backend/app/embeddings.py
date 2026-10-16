import hashlib
import re
from typing import Protocol

import numpy as np

DEFAULT_DIM = 384
_TOKEN = re.compile(r"\w+")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised vectors."""
        ...


class FastEmbedder:
    dim = DEFAULT_DIM

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model
        self._model = None

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from fastembed import TextEmbedding  # lazy: imports and downloads on first use

            self._model = TextEmbedding(model_name=self.model_name)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = np.asarray(list(self._model.embed(texts, batch_size=64)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder for tests and e2e runs."""

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _TOKEN.findall(text.lower()):
                h = int.from_bytes(hashlib.md5(token.encode()).digest()[:8], "big")
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def make_embedder(kind: str) -> Embedder:
    if kind == "fastembed":
        return FastEmbedder()
    if kind == "hash":
        return HashEmbedder()
    raise ValueError(f"Unknown embedder: {kind}")
