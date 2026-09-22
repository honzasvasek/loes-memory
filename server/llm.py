from abc import ABC, abstractmethod
import json
import httpx
from .models import Extraction
from .prompts import EXTRACTION_PROMPT
from .database import now


class LocalLLM(ABC):
    @abstractmethod
    def extract(self, user: str, assistant: str) -> Extraction:
        pass


class OllamaLLM(LocalLLM):
    def __init__(self, url, model):
        self.url, self.model = url.rstrip('/'), model

    def extract(self, user, assistant):
        with httpx.Client(timeout=90, trust_env=False, follow_redirects=False) as client:
            # A localhost Ollama can proxy cloud aliases. Verify local model metadata
            # before handing it any conversation text.
            tags = client.get(self.url + '/api/tags')
            tags.raise_for_status()
            names = {self.model, self.model + ':latest'}
            local = next((m for m in tags.json().get('models', [])
                          if m.get('name') in names or m.get('model') in names), None)
            if not local or local.get('remote_model') or local.get('remote_host') or local.get('size', 0) <= 0:
                raise ValueError('Model ontbreekt lokaal of verwijst naar een remote model')
            response = client.post(self.url + '/api/chat', json={
                'model': self.model, 'stream': False, 'format': Extraction.model_json_schema(),
                'options': {'temperature': 0, 'num_predict': 2048},
                'messages': [
                    {'role': 'system', 'content': EXTRACTION_PROMPT},
                    {'role': 'user', 'content': json.dumps({
                        'observed_at': now(), 'user': user, 'assistant': assistant}, ensure_ascii=False)}]})
            response.raise_for_status()
            return Extraction.model_validate_json(response.json()['message']['content'])
