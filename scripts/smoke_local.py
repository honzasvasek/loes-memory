"""Manual integration test with real local models; isolated temporary database.
Run from repository root: .venv/bin/python -m scripts.smoke_local
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from server.main import create_app
from server.settings import Settings

with TemporaryDirectory() as directory:
    settings = Settings(database_path=Path(directory) / 'smoke.sqlite3')
    with TestClient(create_app(settings), headers={'X-Loes-Memory': 'cli'}) as client:
        result = client.post('/observe', json={
            'user': 'Ik gebruik Linux. Ik prefereer korte directe antwoorden. Ik drink nu koffie.',
            'assistant': 'Ik houd rekening met je voorkeuren.'})
        assert result.status_code == 200, result.text
        memories = client.get('/memories').json()
        assert any('Linux' in m['text'] and m['type'] == 'profile' for m in memories), memories
        assert not any('koffie' in m['text'].lower() for m in memories), memories
        recall = client.post('/recall', json={'message': 'Welk besturingssysteem gebruik ik? Geef passende Linux-instructies.'})
        assert recall.status_code == 200, recall.text
        assert any('Linux' in m for m in recall.json()['memories']), recall.text
        print('Echte lokale extraction, SQLite-opslag en semantische recall geslaagd.')
        print('Memories:', len(memories), '| Recallselectie:', len(recall.json()['memories']))
