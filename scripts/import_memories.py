"""Import chatbot memory JSON locally. Run: python -m scripts.import_memories FILE."""
import argparse
import json
import os
from pathlib import Path
import sys

from pydantic import ValidationError

from server.models import MemoryInput

MAX_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 10000


def load_memories(path: Path) -> list[MemoryInput]:
    """Validate the whole export before opening the database or loading models."""
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Bestand groter dan 10 MiB.')
    try:
        document = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, ValueError):
        raise ValueError('Geen geldige UTF-8 JSON; verwijder eventuele Markdown-codeblokken.') from None
    if isinstance(document, dict):
        if set(document) - {'limitations', 'memories'}:
            raise ValueError('Onbekende velden naast limitations en memories.')
        if 'limitations' in document and not isinstance(document['limitations'], str):
            raise ValueError('limitations moet tekst zijn.')
        document = document.get('memories')
    if not isinstance(document, list) or len(document) > MAX_ITEMS:
        raise ValueError('Verwacht een memories-lijst met maximaal 10000 items.')
    items = []
    for index, item in enumerate(document, 1):
        try:
            items.append(MemoryInput.model_validate(item, strict=True))
        except ValidationError as error:
            # Never print the input values: exports can contain personal data.
            fields = ', '.join('.'.join(map(str, e['loc'])) or 'item'
                               for e in error.errors(include_input=False))
            raise ValueError(f'Ongeldige memory #{index}; controleer: {fields}.') from None
    return items


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Alleen JSON valideren, niets opslaan')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        items = load_memories(args.file)
        print(f'Gevalideerd: {len(items)} memories.')
        if args.dry_run or not items:
            print('Niets gewijzigd.')
            return 0
        # Lazy imports keep validation independent of models and the daemon.
        from server.database import Database
        from server.embeddings import LocalEmbeddings
        from server.memory import MemoryService
        from server.settings import Settings
        settings = Settings()
        service = MemoryService(Database(settings.database_path),
                                LocalEmbeddings(settings.embedding_model), None, settings)
        result = service.import_memories(items)
        print(f"Toegevoegd: {result['added']}; duplicaten overgeslagen: {result['duplicates']}.")
        return 0
    except (OSError, ValueError) as error:
        # ValueErrors from validation are deliberately free of private input.
        if isinstance(error, OSError):
            print(f'Import mislukt ({type(error).__name__}); controleer bestand en rechten.', file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f'Import mislukt ({type(error).__name__}); controleer lokaal model en database. '
              'De importtransactie is niet opgeslagen.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
