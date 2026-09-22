from pathlib import Path
from urllib.parse import urlparse
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_path: Path = Path('data/memory.sqlite3')
    embedding_model: str = 'data/embedding-model'
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen2.5:7b'
    recall_limit: int = Field(5, ge=1, le=20)
    recall_min_similarity: float = Field(.35, ge=0, le=1)
    dedup_threshold: float = Field(.90, ge=0, le=1)
    extraction_min_confidence: float = Field(.65, ge=0, le=1)
    extraction_min_importance: float = Field(.4, ge=0, le=1)
    recall_max_chars: int = Field(2000, ge=100, le=10000)

    @model_validator(mode='after')
    def local_only(self):
        if 'cloud' in self.ollama_model.lower():
            raise ValueError('Ollama-cloudmodellen zijn niet toegestaan')
        url = urlparse(self.ollama_url)
        if url.scheme != 'http' or url.hostname not in {'127.0.0.1', '::1', 'localhost'} or url.username:
            raise ValueError('Ollama moet een lokale HTTP-loopbackserver zijn')
        return self
