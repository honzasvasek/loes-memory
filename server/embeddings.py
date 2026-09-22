import os
from threading import Lock
import numpy as np

# No automatic downloads, usage reporting or Hugging Face network calls at runtime.
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'


class LocalEmbeddings:
    def __init__(self, model):
        self.model_name = model
        self.model = None
        self.lock = Lock()

    def encode(self, text):
        with self.lock:
            if self.model is None:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name, local_files_only=True,
                                                 trust_remote_code=False, device='cpu')
            return self.model.encode(text, normalize_embeddings=True).astype(np.float32)


def similarity(a, b):
    if a.shape != b.shape:
        raise ValueError('Embeddingmodel gewijzigd: gebruik een nieuwe database of herindexeer')
    return float(np.dot(a, b) / max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-12))
