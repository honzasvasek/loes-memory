"""Explicit one-time network setup; never imported by the offline daemon."""
import os
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', trust_remote_code=False)
model.save('data/embedding-model')
print('Embeddingmodel lokaal opgeslagen in data/embedding-model')
