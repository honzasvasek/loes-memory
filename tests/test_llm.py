import httpx
import pytest
from server.llm import OllamaLLM


def test_remote_alias_never_receives_conversation(monkeypatch):
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={'models': [{'name': 'innocent:latest', 'size': 123, 'remote_host': 'https://ollama.com', 'remote_model': 'model'}]})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError):
        OllamaLLM('http://127.0.0.1:11434', 'innocent:latest').extract('private', 'private')
    assert paths == ['/api/tags']


def test_local_model_schema_and_json_validation(monkeypatch):
    paths = []
    def handler(request):
        paths.append(request.url.path)
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'local:latest', 'size': 123}]})
        return httpx.Response(200, json={'message': {'content': '{"memories":[]}'}})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    result = OllamaLLM('http://127.0.0.1:11434', 'local').extract('Hallo', 'Hoi')
    assert result.memories == []
    assert paths == ['/api/tags', '/api/chat']
