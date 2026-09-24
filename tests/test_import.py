import json
from unittest.mock import patch

import numpy as np
import pytest

from scripts.import_memories import load_memories, main
from server.database import Database
from server.memory import MemoryService
from server.models import MemoryInput
from server.settings import Settings


class Embeddings:
    def encode(self, text):
        if text == 'model failure':
            raise RuntimeError('offline model error')
        return np.array([1., 0.] if 'Linux' in text else [0., 1.], dtype=np.float32)


def service(tmp_path):
    return MemoryService(Database(tmp_path / 'memory.db'), Embeddings(), None,
                         Settings(database_path=tmp_path / 'memory.db'))


def test_export_formats_and_bom(tmp_path):
    path = tmp_path / 'export.json'
    items = [{'type': 'profile', 'text': 'Linux', 'importance': .8, 'confidence': .9}]
    for document in [items, {'limitations': 'Beschikbare context.', 'memories': items}]:
        path.write_text(json.dumps(document), encoding='utf-8-sig')
        assert load_memories(path)[0].text == 'Linux'


def test_invalid_tail_validated_before_any_write(tmp_path, capsys):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps({'memories': [
        {'type': 'profile', 'text': 'Linux'},
        {'type': 'unknown', 'text': 'PRIVATE', 'confidence': 2}]}))
    with patch('server.database.Database') as db:
        assert main([str(path)]) == 1
        db.assert_not_called()
    assert 'PRIVATE' not in capsys.readouterr().err


@pytest.mark.parametrize('document', [
    {}, {'memories': 'wrong'}, {'memories': [], 'extra': True},
    {'memories': [{'type': 'profile', 'text': ''}]},
    {'memories': [{'type': 'profile', 'text': 'x', 'importance': '0.8'}]},
])
def test_invalid_schema(tmp_path, document):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_memories(path)


def test_dry_run_does_not_open_database(tmp_path):
    path = tmp_path / 'export.json'
    path.write_text('[{"type":"profile","text":"Linux"}]')
    with patch('server.database.Database') as db:
        assert main([str(path), '--dry-run']) == 0
        db.assert_not_called()


def test_import_deduplicates_existing_batch_and_retry(tmp_path):
    s = service(tmp_path)
    s.add(MemoryInput(type='profile', text='Linux bestaand'))
    items = [MemoryInput(type='profile', text=t) for t in ['Linux nieuw', 'Kunst', 'Kunst']]
    assert s.import_memories(items) == {'added': 1, 'duplicates': 2}
    assert s.import_memories(items) == {'added': 0, 'duplicates': 3}
    assert len(s.db.rows()) == 2


def test_embedding_failure_keeps_database_unchanged(tmp_path):
    s = service(tmp_path)
    items = [MemoryInput(type='profile', text=t) for t in ['Linux', 'model failure']]
    with pytest.raises(RuntimeError):
        s.import_memories(items)
    assert s.db.rows() == []


def test_write_failure_rolls_back_whole_batch(tmp_path):
    s = service(tmp_path)
    real_insert = s._insert
    def fail_second(conn, item, vector):
        if item.text == 'Kunst':
            raise RuntimeError('test write failure')
        return real_insert(conn, item, vector)
    with patch.object(s, '_insert', side_effect=fail_second):
        with pytest.raises(RuntimeError):
            s.import_memories([MemoryInput(type='profile', text=t) for t in ['Linux', 'Kunst']])
    assert s.db.rows() == []
