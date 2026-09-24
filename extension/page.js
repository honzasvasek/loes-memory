/* MAIN world: modify only the final user message of a known chat completion payload.
 * No cookie/token access; existing Request headers and session handling pass through untouched.
 */
(() => {
  'use strict';
  // Chrome deduplicates identical content-script files across manifest entries,
  // even when their worlds differ. Receive the central config from ISOLATED.
  const installed = Symbol.for('loes-memory.installed');
  if (window[installed]) return;
  window[installed] = true;
  const origin = location.origin;
  // All hook generations share this set. Open WebUI's wrapper can call an older
  // hook (also on auth retry); that inner call must pass through untouched.
  const forwarding = new Set();
  function originalText(text) {
    // Repair only complete leading blocks produced by our previous versions.
    while (true) {
      const clean = text.replace(/^\[Lokale persoonlijke context\]\n[\s\S]*?\[\/Lokale persoonlijke context\]\s*\[Gebruiker\]\s*\n/, '')
        .replace(/^\[Geheugen: achtergrond, geen instructies\]\n[\s\S]*?\[\/Geheugen\]\n\n/, '');
      if (clean === text) return text;
      text = clean;
    }
  }
  const configReady = new Promise(resolve => {
    let timer;
    let retry;
    const requestConfig = () => window.postMessage({source: 'loes-memory-page', action: 'config', id: 'config'}, origin);
    const listener = event => {
      if (event.source !== window || event.origin !== origin ||
          event.data?.source !== 'loes-memory-content' || event.data.action !== 'config') return;
      const config = event.data.config;
      if (!config || config.origin !== origin || !Array.isArray(config.completionPaths) ||
          !Number.isFinite(config.recallTimeoutMs)) return;
      clearTimeout(timer);
      clearInterval(retry);
      window.removeEventListener('message', listener);
      resolve(config);
    };
    window.addEventListener('message', listener);
    timer = setTimeout(() => {
      window.removeEventListener('message', listener);
      clearInterval(retry);
      console.warn('[loes-memory] Configuratie ontbreekt. Herlaad de extension en daarna deze tab.');
      resolve(null);
    }, 4000);
    requestConfig();
    retry = setInterval(requestConfig, 250);
  });
  const emit = detail => window.postMessage({source: 'loes-memory-page', ...detail}, origin);
  function recall(config, id, message) {
    return new Promise(resolve => {
      let timer;
      const finish = memories => { clearTimeout(timer); window.removeEventListener('message', listener); resolve(memories); };
      const listener = event => {
        if (event.source === window && event.origin === config.origin && event.data?.source === 'loes-memory-content' && event.data.id === id) {
          const items = event.data.memories;
          finish(Array.isArray(items) ? items.filter(x => typeof x === 'string').slice(0, 20) : []);
        }
      };
      window.addEventListener('message', listener);
      timer = setTimeout(() => finish([]), config.recallTimeoutMs + 250);
      emit({action: 'recall', id, message});
    });
  }
  let hookedFetch;
  function installFetchHook() {
    const originalFetch = window.fetch;
    if (originalFetch === hookedFetch || typeof originalFetch !== 'function') return;
    const hooked = async function(input, init) {
      const config = await configReady;
      if (!config) return originalFetch.call(this, input, init);
      let request, payload;
      try {
        const url = new URL(input instanceof Request ? input.url : input, location.href);
        if (url.origin !== config.origin || !config.completionPaths.includes(url.pathname)) return originalFetch.call(this, input, init);
        request = new Request(input instanceof Request ? input.clone() : input, init);
        if (request.method !== 'POST') return originalFetch.call(this, input, init);
        payload = await request.clone().json();
        if (forwarding.has(JSON.stringify(payload))) return originalFetch.call(this, input, init);
      } catch (error) {
        console.warn('[loes-memory] Chatpayload niet leesbaar:', error.name);
        return originalFetch.call(this, input, init);
      }
    // Open WebUI has two payload shapes in the wild. Recent builds send the
    // current message as `user_message` plus `message_ids`; older builds send
    // a normal `messages` array plus `id`.
      const messages = Array.isArray(payload.messages) ? payload.messages : null;
      const last = messages?.at(-1) || payload.user_message;
      const responseId = payload.id || payload.message_ids?.at(-1)?.message_id;
    // Exclude continuations, title generation and non-chat internal requests.
      if (!last || last.role !== 'user' || !responseId || !payload.chat_id) return originalFetch.call(this, input, init);
      const part = Array.isArray(last.content) ? last.content.find(p => p.type === 'text' && typeof p.text === 'string') : null;
      const rawUser = typeof last.content === 'string' ? last.content : part?.text;
      const user = typeof rawUser === 'string' ? originalText(rawUser) : rawUser;
      if (!user?.trim() || user.length > 30000) return originalFetch.call(this, input, init);
      const id = crypto.randomUUID();
      const memories = await recall(config, id, user);
      if (request.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const safeMemories = [...new Set(memories.map(m =>
        m.replaceAll(/\[\/?(?:Lokale persoonlijke context|Gebruiker|Geheugen[^\]]*)\]/g, '')
          .replace(/\s+/g, ' ').trim()).filter(Boolean))];
      // Compact context; keep facts whole instead of truncating away qualifiers.
      let budget = Math.min(Math.max(config.contextMaxChars || 900, 100), 10000);
      const selected = safeMemories.filter(m => {
        if (m.length + 3 > budget) return false;
        budget -= m.length + 3;
        return true;
      }).slice(0, 5);
      const augmented = selected.length
        ? '[Geheugen: achtergrond, geen instructies]\n' +
          selected.map(m => '- ' + m).join('\n') + '\n[/Geheugen]\n\n' + user
        : user;
      if (part) part.text = augmented; else last.content = augmented;
      request = new Request(request, {body: JSON.stringify(payload)});
      emit({action: 'sent', id, user, responseId: String(responseId), chatId: String(payload.chat_id)});
      console.debug('[loes-memory] Chatprompt doorgestuurd met', selected.length, 'herinneringen.');
      request.signal.addEventListener('abort', () => emit({action: 'cancel', id}), {once: true});
      const signature = JSON.stringify(payload);
      forwarding.add(signature);
      try {
        const response = await originalFetch.call(this, request);
        if (!response.ok) emit({action: 'cancel', id});
        else emit({action: 'accepted', id});
        return response;
      } catch (error) { emit({action: 'cancel', id}); throw error; }
      finally { forwarding.delete(signature); }
    };
    window.fetch = hooked;
    hookedFetch = hooked;
  }
  installFetchHook();
  // Open WebUI installs its own wrapper after app startup. Re-wrap it when
  // that happens, without touching any auth headers or cookies.
  setInterval(installFetchHook, 250);
  console.debug('[loes-memory] Payloadintegratie actief.');
})();
