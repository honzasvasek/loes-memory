import numpy as np
import pytest
from fastapi.testclient import TestClient
from server.main import create_app
from server.models import Extraction
from server.settings import Settings

HEADERS = {'X-Loes-Memory': 'cli'}


class Embeddings:
    def encode(self, text):
        return np.array([1., 0.] if 'Linux' in text else [0., 1.], dtype=np.float32)


class LLM:
    calls = 0
    def extract(self, user, assistant):
        self.calls += 1
        return Extraction.model_validate({'memories': [
            {'type': 'profile', 'text': 'Gebruiker gebruikt Linux.', 'importance': .8, 'confidence': .95},
            {'type': 'episodic', 'text': 'Koffie.', 'importance': .1, 'confidence': .9}]})


@pytest.fixture

def client(tmp_path):
    llm = LLM()
    app = create_app(Settings(database_path=tmp_path / 'test.db'), Embeddings(), llm)
    with TestClient(app, headers=HEADERS) as client:
        yield client, app, llm


def test_health_crud(client):
    c, _, _ = client
    assert c.get('/health').status_code == 200
    item = c.post('/memories', json={'type': 'profile', 'text': 'Linux voorkeur', 'importance': .8}).json()
    mid = item['memory']['id']
    assert item['created']
    assert 'embedding' not in item['memory']
    assert len(c.get('/memories?q=linux&type=profile').json()) == 1
    assert c.get('/memories?type=episodic').json() == []
    assert c.patch(f'/memories/{mid}', json={'importance': .9}).status_code == 200
    assert c.get('/memories').json()[0]['importance'] == .9
    assert c.delete(f'/memories/{mid}').status_code == 204
    assert c.delete(f'/memories/{mid}').status_code == 404
    assert c.post('/memories', json={'type': 'bad', 'text': 'x'}).status_code == 422


def test_recall_dedup_and_threshold(client):
    c, _, _ = client
    assert c.post('/recall', json={'message': 'Linux'}).json() == {'memories': []}
    for text in ['Linux desktop', 'Linux systeem']:
        response = c.post('/memories', json={'type': 'profile', 'text': text}).json()
    assert not response['created']
    assert c.post('/recall', json={'message': 'Linux'}).json()['memories'] == ['Linux desktop']
    assert c.post('/recall', json={'message': 'Onverwant'}).json()['memories'] == []
    assert c.get('/memories').json()[0]['use_count'] == 1


def test_observe_retry_and_privacy(client):
    c, app, llm = client
    body = {'user': 'Ik gebruik Linux RAW-SECRET-MARKER', 'assistant': 'Prima.'}
    assert c.post('/observe', json=body).json()['added'] == 1
    assert c.post('/observe', json=body).json()['status'] == 'duplicate'
    assert llm.calls == 1
    assert len(c.get('/memories').json()) == 1
    assert b'RAW-SECRET-MARKER' not in app.state.memory.db.path.read_bytes()


def test_security(client):
    c, _, _ = client
    assert c.get('/memories', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert c.get('/memories', headers={'Origin': 'https://chat.loes.ai'}).status_code == 403
    assert c.get('/health', headers={'Host': 'evil.example'}).status_code == 400
    assert c.post('/recall', json={'message': 'x'}, headers={'X-Loes-Memory': ''}).status_code == 403
    response = c.options('/recall', headers={'Origin': 'https://chat.loes.ai', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type,x-loes-memory'})
    assert response.headers['access-control-allow-origin'] == 'https://chat.loes.ai'
    assert c.post('/recall', content='x' * 600001).status_code == 415


def test_extraction_failure_retry(client):
    c, app, llm = client
    original = llm.extract
    def fail(*args): raise ValueError('bad JSON')
    llm.extract = fail
    body = {'user': 'Linux', 'assistant': 'ok'}
    assert c.post('/observe', json=body).status_code == 503
    llm.extract = original
    assert c.post('/observe', json=body).json()['added'] == 1


def test_local_ollama_only():
    with pytest.raises(ValueError): Settings(ollama_url='https://remote.example')


def test_background_observation_and_origin_scope(client):
    c, _, _ = client
    response = c.post('/observe?background=true', json={'user': 'Linux', 'assistant': 'ok'}, headers={'Origin': 'https://chat.loes.ai', 'X-Loes-Memory': 'extension'})
    assert response.status_code == 202
    assert response.json()['status'] == 'queued'
    assert c.get('/health').json()['extraction']['last_result'] == 'ok'
    from server.extension_origin import EXTENSION_ORIGIN
    assert c.get('/memories', headers={'Origin': EXTENSION_ORIGIN}).status_code == 403
    assert c.post('/recall', json={'message': 'Linux'}, headers={'Origin': EXTENSION_ORIGIN}).status_code == 200
    assert c.post('/recall', content='x' * 600001, headers={'Content-Type': 'application/json'}).status_code == 413


def test_recall_budget_and_limit(client):
    c, app, _ = client
    app.state.memory.settings.dedup_threshold = 1
    app.state.memory.settings.recall_limit = 2
    for index in range(4):
        c.post('/memories', json={'type': 'profile', 'text': f'Linux {index}', 'importance': index / 4})
    found = c.post('/recall', json={'message': 'Linux'}).json()['memories']
    assert found == ['Linux 3', 'Linux 2']
    app.state.memory.settings.recall_max_chars = 8
    assert len(c.post('/recall', json={'message': 'Linux'}).json()['memories']) == 1


def test_observation_dedup_survives_restart(client):
    c, app, _ = client
    body = {'user': 'Linux', 'assistant': 'ok', 'observation_id': 'chat:message'}
    c.post('/observe', json=body)
    other_llm = LLM()
    with TestClient(create_app(app.state.memory.settings, Embeddings(), other_llm), headers=HEADERS) as again:
        assert again.post('/observe', json=body).json()['status'] == 'duplicate'
        assert other_llm.calls == 0


def test_no_cloud_model():
    with pytest.raises(ValueError): Settings(ollama_model='gemma4:cloud')
