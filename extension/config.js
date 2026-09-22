/* Central compatibility surface: update selectors/endpoints here after Open WebUI changes. */
globalThis.LOES_MEMORY_CONFIG = Object.freeze({
  origin: 'https://chat.loes.ai', daemon: 'http://127.0.0.1:8765',
  completionPaths: ['/api/chat/completions', '/api/v1/chat/completions'],
  recallTimeoutMs: 4000, observeTimeoutMs: 120000, stableMs: 1500,
  responseTimeoutMs: 15 * 60 * 1000,
  selectors: {
    editor: ['[role="textbox"][contenteditable="true"]#chat-input', '#chat-input[contenteditable="true"]', 'textarea#chat-input', '#chat-input [contenteditable="true"]', '#message-input-container textarea', '[contenteditable="true"][data-placeholder]'],
    assistant: ['[data-message-role="assistant"]', '[data-role="assistant"]', '[id^="message-"]:has(#response-content-container)', '[id^="message-"]:has(.assistant-message-profile-image)'],
    content: ['[data-message-content]', '#response-content-container', '.markdown', '.prose'],
    done: ['[data-streaming="false"]', '.copy-response-button', 'button[aria-label="Copy"]', 'button[aria-label="Kopiëren"]'],
    stop: ['#stop-response-button', 'button[aria-label="Stop"]', 'button[aria-label="Stop generating"]', 'button[aria-label="Stoppen"]'],
    exclude: ['button', 'script', 'style', '[aria-hidden="true"]', 'iframe', 'details', '.sr-only'],
  },
});
