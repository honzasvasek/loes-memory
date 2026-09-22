'use strict';
const status = document.querySelector('#status');
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-Loes-Memory': 'manager'}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) { const error = await response.json(); throw new Error(typeof error.detail === 'string' ? error.detail : 'Controleer de invoer.'); }
  return response.status === 204 ? null : response.json();
}
async function act(fn) { try { await fn(); } catch (error) { status.textContent = error.message; } }
async function refresh() {
  const params = new URLSearchParams({q: document.querySelector('#query').value});
  const type = document.querySelector('#filter').value;
  if (type) params.set('type', type);
  const rows = await api('/memories?' + params);
  const list = document.querySelector('#memories'); list.replaceChildren();
  for (const row of rows) {
    const article = document.createElement('article');
    const text = document.createElement('p'); text.textContent = row.text;
    const meta = document.createElement('small'); meta.textContent = `${row.type} · zekerheid ${row.confidence} · ${row.use_count}× gebruikt · ${new Date(row.created_at).toLocaleString('nl')}`;
    const label = document.createElement('label'); label.textContent = 'Belang ';
    const input = document.createElement('input'); Object.assign(input, {type: 'number', min: '0', max: '1', step: '.05', value: String(row.importance)}); label.append(input);
    const save = document.createElement('button'); save.textContent = 'Belang opslaan';
    save.onclick = () => act(async () => { if (!input.reportValidity() || !input.value) return; await api(`/memories/${row.id}`, 'PATCH', {importance: Number(input.value)}); status.textContent = 'Opgeslagen.'; await refresh(); });
    const remove = document.createElement('button'); remove.textContent = 'Verwijderen';
    remove.onclick = () => act(async () => { await api(`/memories/${row.id}`, 'DELETE'); status.textContent = 'Verwijderd.'; await refresh(); });
    article.append(text, meta, label, save, remove); list.append(article);
  }
  if (!rows.length) list.textContent = 'Geen herinneringen gevonden.';
}
document.querySelector('#search').onsubmit = event => { event.preventDefault(); act(refresh); };
document.querySelector('#filter').onchange = () => act(refresh);
document.querySelector('#add').onsubmit = event => {
  event.preventDefault(); const form = event.target; const data = new FormData(form);
  act(async () => { const result = await api('/memories', 'POST', {type: data.get('type'), text: data.get('text'), importance: Number(data.get('importance'))}); status.textContent = result.created ? 'Toegevoegd.' : 'Vergelijkbare herinnering bestaat al; bestaande behouden.'; form.reset(); await refresh(); });
};
act(refresh);
