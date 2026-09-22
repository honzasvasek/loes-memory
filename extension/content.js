(() => {
  'use strict';
  const config = globalThis.LOES_MEMORY_CONFIG;
  const pending = new Map();
  let editorSeen = false;
  const log = (...args) => console.debug('[loes-memory]', ...args);
  const first = (root, selectors) => selectors.map(s => root.querySelector(s)).find(Boolean);
  const visible = element => !!element && element.getClientRects().length > 0;
  const dom = {
    editor: () => first(document, config.selectors.editor),
    assistants: () => [...new Set(config.selectors.assistant.flatMap(s => [...document.querySelectorAll(s)]))],
    response(id) { return this.assistants().find(el => el.id === `message-${id}` || el.dataset.messageId === id); },
    text(element) {
      const content = first(element, config.selectors.content);
      if (!content) return '';
      const copy = content.cloneNode(true);
      for (const selector of config.selectors.exclude) copy.querySelectorAll(selector).forEach(el => el.remove());
      // Preserve block/code boundaries without relying on innerText of a detached element.
      copy.querySelectorAll('br').forEach(el => el.replaceWith('\n'));
      copy.querySelectorAll('p,div,li,pre,h1,h2,h3,tr').forEach(el => el.append('\n'));
      return (copy.textContent || '').trim();
    },
    done(element) {
      if (config.selectors.stop.some(s => [...document.querySelectorAll(s)].some(visible))) return false;
      return element.matches('[data-streaming="false"]') || !!first(element, config.selectors.done);
    },
  };
  async function rpc(action, body) {
    try { return await chrome.runtime.sendMessage({action, body}); }
    catch { return {ok: false}; }
  }
  window.addEventListener('message', async event => {
    const data = event.data;
    if (event.source !== window || event.origin !== config.origin || data?.source !== 'loes-memory-page' || typeof data.id !== 'string') return;
    if (data.action === 'recall' && typeof data.message === 'string' && data.message.length <= 30000) {
      const result = await rpc('recall', {message: data.message});
      if (!result?.ok) console.warn('[loes-memory] Recall niet beschikbaar; normaal chatten zonder context.');
      window.postMessage({source: 'loes-memory-content', id: data.id, memories: result?.data?.memories || []}, config.origin);
    } else if (data.action === 'sent' && typeof data.user === 'string' && typeof data.responseId === 'string') {
      if (pending.size >= 8) { log('Te veel gelijktijdige antwoorden; observatie overgeslagen.'); return; }
      const existing = dom.response(data.responseId);
      pending.set(data.id, {...data, initialText: existing ? dom.text(existing) : null, sawStreaming: false, path: location.pathname, started: Date.now(), accepted: false, lastText: '', changed: Date.now()});
    } else if (data.action === 'accepted') {
      const turn = pending.get(data.id); if (turn) turn.accepted = true;
    } else if (data.action === 'cancel') pending.delete(data.id);
  });
  async function observe(turn, assistant) {
    // Keep retry data in memory only. Same id makes daemon retries idempotent.
    const body = {user: turn.user, assistant, observation_id: `${turn.chatId}:${turn.responseId}`};
    for (let attempt = 0; attempt < 3; attempt++) {
      const result = await rpc('observe', body);
      if (result?.ok) { log('Lokale observatie:', result.data.status); return; }
      if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)));
    }
    console.warn('[loes-memory] Observatie mislukt; ruwe tekst wordt niet bewaard. Controleer lokale modellen.');
  }
  function scan() {
    if (!editorSeen && dom.editor()) { editorSeen = true; log('Open WebUI-invoerveld gevonden.'); }
    for (const [id, turn] of pending) {
      const currentChat = location.pathname.match(/^\/c\/([^/]+)/)?.[1];
      if ((currentChat && currentChat !== turn.chatId) ||
          (location.pathname !== turn.path && !currentChat) || Date.now() - turn.started > config.responseTimeoutMs) {
        pending.delete(id); log('Observatie beëindigd na navigatie of timeout.'); continue;
      }
      if (!turn.accepted) continue;
      const element = dom.response(turn.responseId);
      if (!element) continue;
      const text = dom.text(element);
      const done = dom.done(element);
      if (!done) turn.sawStreaming = true;
      if (turn.initialText !== null && text === turn.initialText && !turn.sawStreaming) continue;
      if (text !== turn.lastText) { turn.lastText = text; turn.changed = Date.now(); }
      // Require an explicit completion marker as well as stable text. A streaming pause isn't completion.
      if (!text || !done || Date.now() - turn.changed < config.stableMs) continue;
      pending.delete(id);
      if (text.length > 100000) { log('Antwoord te lang; observatie overgeslagen.'); continue; }
      void observe(turn, text);
    }
  }
  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => { scheduled = false; scan(); }, 200);
  });
  function start() {
    observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['data-streaming']});
    setInterval(scan, 750);
    scan();
    log('DOM-observatie actief; alleen nieuwe, afgeronde antwoorden worden verwerkt.');
  }
  if (document.documentElement) start(); else document.addEventListener('DOMContentLoaded', start, {once: true});
})();
