import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

function harness(memories = ['Gebruiker gebruikt Linux.']) {
  const listeners = new Set(), events = [], calls = [];
  const context = {console: {debug() {}, warn() {}}, Request, URL, DOMException, crypto, setTimeout, clearTimeout, location: {href: 'https://chat.loes.ai/c/chat1', origin: 'https://chat.loes.ai'}};
  context.window = {
    addEventListener(type, fn) { listeners.add(fn); },
    removeEventListener(type, fn) { listeners.delete(fn); },
    postMessage(data) {
      events.push(data);
      if (data.action === 'config') queueMicrotask(() => {
        for (const fn of listeners) fn({source: context.window, origin: 'https://chat.loes.ai', data: {source: 'loes-memory-content', action: 'config', config: context.LOES_MEMORY_CONFIG}});
      });
      if (data.action === 'recall') queueMicrotask(() => {
        for (const fn of listeners) fn({source: context.window, origin: 'https://chat.loes.ai', data: {source: 'loes-memory-content', id: data.id, memories}});
      });
    },
    async fetch(...args) { calls.push(new Request(...args)); return new Response('ok'); },
  };
  vm.createContext(context);
  for (const file of ['config.js', 'page.js']) vm.runInContext(fs.readFileSync(`extension/${file}`, 'utf8'), context);
  return {context, events, calls};
}
const body = () => ({id: 'answer1', chat_id: 'chat1', messages: [{role: 'system', content: 'system'}, {role: 'user', content: 'old'}, {role: 'assistant', content: 'old answer'}, {role: 'user', content: 'Mijn vraag'}]});

test('only final user payload changes; original object, session and UI data stay intact', async () => {
  const h = harness(); const payload = body();
  await h.context.window.fetch('https://chat.loes.ai/api/chat/completions', {method: 'POST', credentials: 'include', headers: {'X-Test': 'preserve'}, body: JSON.stringify(payload)});
  const result = await h.calls[0].json();
  assert.equal(payload.messages.at(-1).content, 'Mijn vraag');
  assert.deepEqual(result.messages.slice(0, -1), payload.messages.slice(0, -1));
  assert.match(result.messages.at(-1).content, /Gebruiker gebruikt Linux/);
  assert.equal(h.calls[0].credentials, 'include');
  assert.equal(h.calls[0].headers.get('X-Test'), 'preserve');
  assert.equal(h.events.find(e => e.action === 'sent').user, 'Mijn vraag');
});
test('empty recall sends original prompt', async () => {
  const h = harness([]);
  await h.context.window.fetch(new Request('https://chat.loes.ai/api/chat/completions', {method: 'POST', body: JSON.stringify(body())}));
  assert.deepEqual(await h.calls[0].json(), body());
});
test('uploads preserved and text part augmented', async () => {
  const h = harness(), payload = body();
  payload.messages.at(-1).content = [{type: 'text', text: 'Mijn vraag'}, {type: 'image_url', image_url: {url: 'data:image/png;base64,abc'}}];
  await h.context.window.fetch('https://chat.loes.ai/api/chat/completions', {method: 'POST', body: JSON.stringify(payload)});
  const result = await h.calls[0].json();
  assert.deepEqual(result.messages.at(-1).content[1], payload.messages.at(-1).content[1]);
  assert.match(result.messages.at(-1).content[0].text, /Lokale persoonlijke context/);
});

test('current Open WebUI user_message payload is augmented and tracked', async () => {
  const h = harness();
  const payload = {
    chat_id: 'chat1',
    user_message: {id: 'user1', role: 'user', content: 'Mijn vraag'},
    message_ids: [{model_id: 'model', message_id: 'answer1'}],
    messages: undefined,
  };
  await h.context.window.fetch('https://chat.loes.ai/api/chat/completions', {method: 'POST', body: JSON.stringify(payload)});
  const result = await h.calls[0].json();
  assert.match(result.user_message.content, /Lokale persoonlijke context/);
  assert.equal(result.message_ids[0].message_id, 'answer1');
  assert.equal(h.events.find(e => e.action === 'sent').responseId, 'answer1');
});
test('unrelated calls and assistant continuations are not intercepted', async () => {
  const h = harness();
  await h.context.window.fetch('https://chat.loes.ai/api/v1/chats', {method: 'POST', body: '{}'});
  const payload = body(); payload.messages.push({role: 'assistant', content: 'continue'});
  await h.context.window.fetch('https://chat.loes.ai/api/chat/completions', {method: 'POST', body: JSON.stringify(payload)});
  assert.equal(h.events.filter(e => e.action !== 'config').length, 0); assert.equal(h.calls.length, 2);
});
test('cancelled request never reaches Loes', async () => {
  const h = harness(), controller = new AbortController(); controller.abort();
  await assert.rejects(h.context.window.fetch('https://chat.loes.ai/api/chat/completions', {method: 'POST', signal: controller.signal, body: JSON.stringify(body())}), {name: 'AbortError'});
  assert.equal(h.calls.length, 0);
});

test('unsupported Request body remains readable by original fetch', async () => {
  const h = harness(), payload = {messages: [{role: 'assistant', content: 'done'}]};
  await h.context.window.fetch(new Request('https://chat.loes.ai/api/chat/completions', {method: 'POST', body: JSON.stringify(payload)}));
  assert.deepEqual(await h.calls[0].json(), payload);
});

test('background proxy rejects other sites and cannot fetch arbitrary URLs', async () => {
  let listener, fetched;
  const context = {console, URL, AbortSignal, importScripts() {}, chrome: {runtime: {id: 'our-id', onMessage: {addListener(fn) { listener = fn; }}}},
    fetch: async (url, options) => { fetched = {url, options}; return new Response('{"memories":[]}'); }};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('extension/config.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('extension/background.js', 'utf8'), context);
  const sender = {id: 'our-id', frameId: 0, tab: {}, url: 'https://evil.example'};
  assert.equal(listener({action: 'recall', body: {message: 'x'}}, sender, () => {}), false);
  sender.url = 'https://chat.loes.ai/c/123';
  assert.equal(listener({action: 'memories'}, sender, () => {}), false);
  const response = await new Promise(resolve => listener({action: 'recall', body: {message: 'x'}, url: 'https://evil.example'}, sender, resolve));
  assert.equal(response.ok, true);
  assert.equal(fetched.url, 'http://127.0.0.1:8765/recall');
  assert.equal(fetched.options.credentials, 'omit');
});
