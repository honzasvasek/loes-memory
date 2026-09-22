import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from threading import BoundedSemaphore
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from .database import Database, public
from .embeddings import LocalEmbeddings
from .extension_origin import EXTENSION_ORIGIN
from .llm import OllamaLLM
from .memory import MemoryService
from .models import MemoryInput, ImportanceUpdate, RecallInput, Observation
from .settings import Settings

LOCAL_ORIGIN = 'http://127.0.0.1:8765'
LOES_ORIGIN = 'https://chat.loes.ai'


def create_app(settings=None, embeddings=None, llm=None):
    settings = settings or Settings()
    db = Database(settings.database_path)
    service = MemoryService(db, embeddings or LocalEmbeddings(settings.embedding_model),
                            llm or OllamaLLM(settings.ollama_url, settings.ollama_model), settings)
    app = FastAPI(title='Loes Memory', version='0.1.0', docs_url=None, redoc_url=None)
    app.state.memory = service
    queue_slots = BoundedSemaphore(8)
    extraction_status = {"last_result": "none"}
    app.add_middleware(CORSMiddleware, allow_origins=[LOES_ORIGIN, LOCAL_ORIGIN, EXTENSION_ORIGIN],
                       allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                       allow_headers=['Content-Type', 'X-Loes-Memory'], allow_credentials=False)

    @app.middleware('http')
    async def privacy_boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        path = request.url.path
        # CORS alone is not an access check. Remote Loes/extension clients only recall/observe.
        if origin and origin not in {LOES_ORIGIN, LOCAL_ORIGIN, EXTENSION_ORIGIN}:
            return JSONResponse({'detail': 'Origin niet toegestaan'}, status_code=403)
        remote_client = origin in {LOES_ORIGIN, EXTENSION_ORIGIN} or request.headers.get('x-loes-memory') == 'extension'
        if remote_client and path not in {'/recall', '/observe', '/health'}:
            return JSONResponse({'detail': 'Alleen lokaal beheer'}, status_code=403)
        if not origin and request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-site request geweigerd'}, status_code=403)
        if request.method in {'POST', 'PATCH', 'DELETE'}:
            if request.headers.get('x-loes-memory') not in {'extension', 'manager', 'cli'}:
                return JSONResponse({'detail': 'X-Loes-Memory header vereist'}, status_code=403)
            if request.method != 'DELETE' and request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'JSON vereist'}, status_code=415)
        # Bound request bodies before JSON validation (including chunked requests).
        if request.method in {'POST', 'PATCH'}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 600_000:
                    return JSONResponse({'detail': 'Request te groot'}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; connect-src 'self'"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.get('/', response_class=HTMLResponse)
    def index():
        return (Path(__file__).parent / 'templates/index.html').read_text()

    @app.get('/assets/{filename}')
    def asset(filename: str):
        from fastapi.responses import Response
        if filename not in {'manage.js', 'style.css'}:
            raise HTTPException(404)
        return Response((Path(__file__).parent / 'templates' / filename).read_text(),
                        media_type='text/javascript' if filename.endswith('.js') else 'text/css')

    @app.get('/health')
    def health():
        with db.connect() as conn:
            conn.execute('SELECT 1')
        return {'status': 'ok', 'version': '0.1.0', 'embedding_model': settings.embedding_model,
                'embedding_loaded': getattr(service.embeddings, 'model', None) is not None,
                'ollama_model': settings.ollama_model, 'extraction': extraction_status.copy(),
                'note': 'Database bereikbaar; modellen worden bij gebruik geladen, Ollama niet getest.'}

    @app.get('/memories')
    def memories(q: str = '', type: str | None = None):
        if type not in {None, 'profile', 'episodic'}:
            raise HTTPException(422, 'Ongeldig type')
        return [public(row) for row in db.rows(q, type)]

    @app.post('/memories', status_code=201)
    def add(item: MemoryInput):
        try:
            memory, created = service.add(item)
            return {'memory': memory, 'created': created}
        except Exception as error:
            logging.warning('Memory add failed: %s', type(error).__name__)
            raise HTTPException(503, 'Lokaal embeddingmodel niet beschikbaar; controleer installatie') from None

    @app.patch('/memories/{memory_id}')
    def update(memory_id: int, item: ImportanceUpdate):
        if not db.update_importance(memory_id, item.importance):
            raise HTTPException(404, 'Memory niet gevonden')
        return {'status': 'ok'}

    @app.delete('/memories/{memory_id}', status_code=204)
    def delete(memory_id: int):
        if not db.delete(memory_id):
            raise HTTPException(404, 'Memory niet gevonden')

    @app.post('/recall')
    def recall(item: RecallInput):
        try:
            return {'memories': service.recall(item.message)}
        except Exception as error:
            logging.warning('Recall failed: %s', type(error).__name__)
            raise HTTPException(503, 'Lokale embeddings niet beschikbaar') from None

    @app.post('/observe')
    def observe(item: Observation, tasks: BackgroundTasks, background: bool = False):
        # Reply promptly to Chrome: service-worker fetches cannot wait for a cold LLM indefinitely.
        if background:
            if not queue_slots.acquire(blocking=False):
                raise HTTPException(503, 'Lokale extractiewachtrij vol')
            def extract_later():
                try:
                    result = service.observe(item)
                    extraction_status['last_result'] = result['status']
                except Exception as error:
                    extraction_status['last_result'] = 'error'
                    logging.warning('Background extraction failed: %s', type(error).__name__)
                finally:
                    queue_slots.release()
            tasks.add_task(extract_later)
            return JSONResponse({'status': 'queued'}, status_code=202)
        try:
            return service.observe(item)
        except Exception as error:
            logging.warning('Observe failed: %s', type(error).__name__)
            raise HTTPException(503, 'Lokale extraction mislukt; controleer Ollama en embeddings') from None

    return app
