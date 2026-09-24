"""Load the actual MV3 extension in Chromium, with fake Loes and a real HTTP daemon.

No logged-in browser profile, Loes request, model download or production database is used.
"""
import os
from pathlib import Path
import shutil
import socket
import threading
import time

import numpy as np
from playwright.sync_api import sync_playwright
import uvicorn

from server.main import create_app
from server.models import Extraction, MemoryInput
from server.settings import Settings


class StubEmbeddings:
    def encode(self, text):
        return np.array([1., 0.], dtype=np.float32)


class StubLLM:
    def __init__(self):
        self.calls = []

    def extract(self, user, assistant):
        self.calls.append((user, assistant))
        return Extraction(memories=[MemoryInput(type='episodic', text='Een testgesprek afgerond.')])


def test_installed_extension_recall_observe_and_offline_fallback(tmp_path):
    extension = tmp_path / 'extension'
    shutil.copytree('extension', extension)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    config = extension / 'config.js'
    config.write_text(config.read_text().replace('http://127.0.0.1:8765', f'http://127.0.0.1:{port}'))
    llm = StubLLM()
    app = create_app(Settings(database_path=tmp_path / 'memory.db'), StubEmbeddings(), llm)
    app.state.memory.add(MemoryInput(type='profile', text='De gebruiker gebruikt Linux.'))
    requests = []

    @app.middleware('http')
    async def record(request, call_next):
        response = await call_next(request)
        requests.append((request.url.path, request.headers.get('origin'), response.status_code))
        return response

    server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE', p.chromium.executable_path)
            assert Path(executable).exists(), 'Run .venv/bin/playwright install chromium or set PLAYWRIGHT_CHROMIUM_EXECUTABLE'
            context = p.chromium.launch_persistent_context(
                tmp_path / 'browser', executable_path=executable, headless=True,
                args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}', '--no-sandbox'],
            )
            try:
                page = context.new_page()
                logs, payloads = [], []
                page.on('console', lambda message: logs.append(message.text))

                def fake_loes(route):
                    if route.request.resource_type == 'document':
                        route.fulfill(body='''<!doctype html><div id="chat-input" contenteditable="true"></div>
                            <main><div id="message-old"><div id="response-content-container">Oud antwoord</div>
                            <button class="copy-response-button">Copy</button></div></main>''',
                            content_type='text/html', headers={'Content-Security-Policy': "default-src 'self'; script-src 'self'"})
                    elif route.request.url.endswith('/api/chat/completions'):
                        payloads.append(route.request.post_data_json)
                        route.fulfill(json={'ok': True})
                    else:
                        route.fulfill(status=404, body='')

                page.route('https://chat.loes.ai/**', fake_loes)
                page.goto('https://chat.loes.ai/c/test-chat')
                # Reproduce the actual site's nested fetch wrappers.
                for _ in range(2):
                    page.evaluate('''() => {
                        const previous = window.fetch;
                        window.fetch = (input, init) => previous(new Request(
                            input instanceof Request ? input : new URL(input, location.href), init));
                    }''')
                    page.wait_for_timeout(350)
                original = 'Geef me Linux-instructies.'
                page.locator('#chat-input').fill(original)
                send = '''async ({id, text}) => {
                    await fetch('/api/chat/completions', {
                        method:'POST', headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({chat_id:'test-chat',id,messages:[{role:'user',content:text}]})
                    });
                }'''
                page.evaluate(send, {'id': 'answer', 'text': original})
                assert any(path == '/recall' and status == 200 for path, _, status in requests), logs
                assert 'De gebruiker gebruikt Linux.' in payloads[0]['messages'][0]['content'], logs
                assert len([p for p, _, _ in requests if p == '/recall']) == 1
                assert payloads[0]['messages'][0]['content'].count('[Geheugen:') == 1
                assert page.locator('#chat-input').inner_text() == original
                page.evaluate('''() => {
                    document.querySelector('main').insertAdjacentHTML('beforeend',
                        '<div id="message-answer"><div id="response-content-container">Halverwege</div></div><button aria-label="Stop">Stop</button>');
                }''')
                page.wait_for_timeout(2000)
                assert not llm.calls
                page.evaluate('''() => {
                    document.querySelector('#message-answer #response-content-container').textContent='Het volledige antwoord.';
                    document.querySelector('[aria-label="Stop"]').remove();
                    document.querySelector('#message-answer').insertAdjacentHTML('beforeend','<button class="copy-response-button">Copy</button>');
                }''')
                deadline = time.monotonic() + 10
                while not llm.calls and time.monotonic() < deadline:
                    page.wait_for_timeout(100)
                assert llm.calls == [(original, 'Het volledige antwoord.')], logs
                page.wait_for_timeout(2000)
                assert len(llm.calls) == 1
                with app.state.memory.db.connect() as db:
                    assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 1
                assert any(path == '/observe' and status == 202 for path, _, status in requests)
                assert all(origin and origin.startswith('chrome-extension://') for _, origin, _ in requests)

                # With the daemon stopped, send the original prompt once and preserve the UI.
                server.should_exit = True
                thread.join(5)
                page.evaluate(send, {'id': 'offline-answer', 'text': original})
                assert len(payloads) == 2
                assert payloads[1]['messages'][0]['content'] == original
                assert page.locator('#chat-input').inner_text() == original
                assert any('Recall niet beschikbaar' in line for line in logs)
            finally:
                context.close()
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
