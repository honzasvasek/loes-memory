'use strict';
importScripts('config.js');
const config = globalThis.LOES_MEMORY_CONFIG;
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  // Never act as a generic HTTP proxy. Only our content script on the exact Loes origin.
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || !sender.tab ||
      !sender.url || new URL(sender.url).origin !== config.origin) return false;
  if (!['recall', 'observe'].includes(message?.action)) return false;
  const body = message.body;
  if (!body || (message.action === 'recall' && (typeof body.message !== 'string' || body.message.length > 30000)) ||
      (message.action === 'observe' && (typeof body.user !== 'string' || typeof body.assistant !== 'string' || body.user.length > 30000 || body.assistant.length > 100000))) return false;
  const timeout = message.action === 'recall' ? config.recallTimeoutMs : config.observeTimeoutMs;
  fetch(`${config.daemon}/${message.action}${message.action === "observe" ? "?background=true" : ""}`, {
    method: 'POST', credentials: 'omit', redirect: 'error', cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-Loes-Memory': 'extension'},
    body: JSON.stringify(body), signal: AbortSignal.timeout(timeout),
  }).then(async response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    reply({ok: true, data: await response.json()});
  }).catch(error => { console.warn('[loes-memory] Lokaal geheugen onbereikbaar:', error.name); reply({ok: false}); });
  return true;
});
