# Loes Memory 0.1

Een lokaal persoonlijk geheugen voor **https://chat.loes.ai**, met een Manifest V3-extension, FastAPI, SQLite, sentence-transformers en Ollama. Geen Loes-API-key, serveraanpassing of toegang tot cookies nodig.

## Starten

Vereist: Python 3.12+, `python3-venv`, Chrome 111+ en een lokaal draaiende Ollama-installatie. De embeddings gebruiken de CPU. Reken op ongeveer 2 GB voor de Python-omgeving en het embeddingmodel, plus het gekozen Ollama-model.

```bash
./run.sh
```

Dit maakt `.venv` en `.env`, installeert dependencies en start op **127.0.0.1:8765**. Eerste installatie vereist internet. Volgende starts installeren alleen opnieuw als `requirements.txt` is gewijzigd. Stop de server voor de eenmalige modelinstallatie:

```bash
.venv/bin/python scripts/download_model.py
ollama pull qwen2.5:7b
```

Zet `OLLAMA_MODEL` in `.env` op een **lokaal geïnstalleerd model**. `qwen2.5:7b` is de voorbeeldconfiguratie; een bestaand model zoals `llama3.2:latest` kan ook. Zorg dat Ollama draait (`ollama serve` als er nog geen service draait). Gebruik voor Ollama `OLLAMA_NO_CLOUD=1`; de daemon weigert bovendien modelnamen met `cloud` en controleert vóór iedere extractie via `/api/tags` dat het model lokaal aanwezig is en geen remote model/host vermeldt. Configureer geen alias die naar een cloudmodel verwijst.

Start vervolgens weer `./run.sh`. Open [het lokale beheer](http://127.0.0.1:8765/) en volg [install-extension.md](install-extension.md). Herlaad daarna de Loes-tab.

Het embeddingmodel wordt **nooit automatisch gedownload tijdens chatten**. Het downloadscript haalt eenmalig `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` op en slaat dit onder `data/embedding-model` op. Daarna gebruikt de daemon uitsluitend lokale bestanden. Een eerste recall kan nog model-laadtijd hebben; volgende recalls zijn sneller.

## Werking

1. `page.js` onderschept uitsluitend `fetch` naar de bekende Open WebUI-completionpaden op chat.loes.ai. Alleen gewone chatrequests met `chat_id`, antwoord-`id` en een laatste user-bericht worden behandeld.
2. `content.js` vraagt via de extension-serviceworker `/recall` op. De daemon selecteert standaard maximaal vijf relevante herinneringen, maximaal 2.000 tekens.
3. Alleen de laatste user-tekst in de netwerkpayload krijgt de geselecteerde context. Het invoerveld en de weergegeven gebruikersprompt worden niet aangepast. Bijlagen, eerdere berichten en de bestaande sessie blijven intact. De extension leest of bewaart geen credentials.
4. Een `MutationObserver` volgt het antwoord met de bijbehorende message-ID. Alleen stabiele tekst met een completionmarker wordt doorgestuurd naar `/observe`. Pauzes tijdens streaming zijn op zichzelf geen completionmarker. Knoppen, verborgen tekst en `details` (zoals redeneringen) worden uitgesloten.
5. Ollama selecteert nuttige feiten/gebeurtenissen via een JSON-schema. Validatie en drempels verwijderen onzekere of onbelangrijke extracties. SQLite bewaart memories en een hash per verwerkte observatie.

De browser gebruikt `/observe?background=true`: de daemon bevestigt direct met `202 queued`, zodat een koud LLM de Chrome-serviceworker niet laat verlopen. Er passen maximaal acht observaties tegelijk in de wachtrij; verwerking is serieel. De wachtrij staat uitsluitend in RAM. Na stoppen/crashen verdwijnen onafgemaakte observaties. Een geaccepteerde achtergrondtaak die mislukt wordt gelogd, maar niet automatisch opnieuw verwerkt. `/health` toont `extraction.last_result`; een `queued`-melding is dus geen bevestiging dat extraction is gelukt.

## Beheer en API

De beheerpagina biedt zoeken, typefilter, toevoegen, verwijderen en importance aanpassen. HTML en vanilla JavaScript, geen buildstap. Tekst wordt veilig als tekst weergegeven.

| Endpoint | Functie |
|---|---|
| `GET /health` | Databasecontrole en modelconfiguratie; geen garantie dat Ollama/model geladen is |
| `POST /recall` | `{"message":"Welke Linux-tools passen bij mij?"}` → `{"memories":["..."]}` |
| `POST /observe` | `{"user":"...","assistant":"..."}` → resultaat na verwerking |
| `POST /observe?background=true` | Zelfde input, onmiddellijke bevestiging van lokale wachtrij |
| `GET /memories?q=Linux&type=profile` | Zoeken/filteren, zonder embeddings in de response |
| `POST /memories` | `{"type":"profile","text":"Ik gebruik Linux.","importance":0.8}` |
| `PATCH /memories/{id}` | `{"importance":0.9}` |
| `DELETE /memories/{id}` | Verwijderen |

Muterende requests vereisen `X-Loes-Memory: cli` (of de manager-/extensionwaarde). POST/PATCH vereisen `Content-Type: application/json`. Bijvoorbeeld:

```bash
curl http://127.0.0.1:8765/memories \
  -H 'Content-Type: application/json' -H 'X-Loes-Memory: cli' \
  -d '{"type":"profile","text":"Ik gebruik Linux.","importance":0.8}'
```

Deze header is een bescherming tegen ongewenste browserrequests, geen API-key of authenticatie tegen lokale processen. De beheerpagina is bestemd voor dezelfde computer.

## Instellingen

Zie `.env.example`. Start de daemon opnieuw na een wijziging.

- `RECALL_LIMIT=5`, `RECALL_MIN_SIMILARITY=0.35`, `RECALL_MAX_CHARS=2000` beperken wat naar Loes gaat.
- `DEDUP_THRESHOLD=0.90`: boven deze cosinesimilarity blijft de bestaande memory behouden. Exact dezelfde tekst wordt ook gededupliceerd. Deduplicatie gebeurt per type en onder een lock.
- `EXTRACTION_MIN_IMPORTANCE=0.40` en `EXTRACTION_MIN_CONFIDENCE=0.65` filteren extracties.
- `OLLAMA_MODEL` en `OLLAMA_URL` kiezen een lokaal model/server. Alleen loopback-HTTP is toegestaan; proxies en redirects zijn uitgeschakeld.
- `EMBEDDING_MODEL` verwijst naar lokale modelbestanden. Gebruik bij modelwissel een nieuwe `DATABASE_PATH`; bestaande vectors zijn niet uitwisselbaar. Overschrijf ook niet stilzwijgend het model op hetzelfde pad.

Recall gebruikt:

```text
0.65 * semantic_similarity + 0.20 * importance + 0.10 * recency + 0.05 * frequency
recency = exp(-dagen_sinds_updated_at / 90)
frequency = min(log(1 + use_count) / log(21), 1)
```

Similarity onder de drempel wordt vóór ranking uitgesloten. Een lege selectie is normaal. Coëfficiënten staan bijeen in `server/memory.py`. `last_used_at` en `use_count` registreren recall-selectie; ze garanderen niet dat het bericht daarna succesvol naar Loes is verzonden.

## Privacygrens

- Het volledige **lokale geheugen** wordt nooit naar Loes gestuurd. De browser mag via de daemon alleen recall, observe en health gebruiken; beheer is lokaal.
- De extra verwerking van gesprekstekst gebeurt lokaal. Ruwe user/assistant-tekst wordt niet door deze daemon op schijf opgeslagen. Er is geen lokale volledige gespreksarchivering in deze versie.
- **Je gewone chats gaan, zoals nu, naar de externe Loes-server.** Dit systeem kan die bestaande geschiedenis, serverlogs of modelverwerking niet lokaal maken. Ook de geselecteerde context is onderdeel van de verzonden prompt en kan daar worden opgeslagen. Alleen de extra geheugenopslag/extraction is lokaal.
- Runtime-embeddings zijn offline, telemetry staat uit, de enige daemon-HTTP-client praat met lokale Ollama. Downloads van dependencies en modellen zijn afzonderlijke installatiehandelingen.
- De serviceworker gebruikt uitsluitend loopback en controleert afzender, tab, frame en origin. Geen cookies-, storage- of webRequest-permission. Chrome-hostpermissions kunnen geen poort afdwingen; de implementatie gebruikt alleen poort 8765.
- CORS staat alleen Loes, lokaal beheer en de vaste eigen extension-origin toe. Hostcontrole beperkt DNS-rebinding. Requests met een andere Origin worden daadwerkelijk geweigerd. De manifest-public-key zorgt voor een stabiele extension-ID; dit is geen geheime sleutel.
- SQLite is niet versleuteld. `run.sh` gebruikt `umask 077`. Andere processen onder je eigen account kunnen bestanden en localhost lezen. Verwijderen is logisch verwijderen, geen gegarandeerd forensisch wissen van SQLite/WAL/back-ups.

## Grenzen van de proof-of-concept

De integratie is afgestemd op de publieke Open WebUI-broncode, niet op een vastgestelde versie op chat.loes.ai. In `extension/config.js` staan alle selectors, completionpaden en timeouts. De site moet `window.fetch` en het ondersteunde payloadformaat gebruiken. XHR, andere endpoints, chatvervolging met een laatste assistant-bericht, voice flows en afwijkende forks kunnen de integratie omzeilen. Er is bewust geen automatische DOM-herschrijffallback die onbedoeld tekst kan versturen. Gebruik voor de eerste proef een normaal tekstgesprek met één model.

De extension observeert alleen nieuwe antwoorden zolang de tab open blijft. Historische gesprekken worden niet geïmporteerd. Navigatie naar een ander gesprek, stoppen, errors en timeout kunnen een observatie overslaan. Bij daemonuitval gaat de prompt na maximaal circa 4,25 seconden zonder herinneringen door. Een DOM-update kan observatie breken; kijk naar `[loes-memory]` in de Chrome-console.

Extractie en semantische deduplicatie zijn heuristisch. Een gewijzigde voorkeur kan te sterk lijken op een oude: deze versie behoudt conservatief de bestaande tekst in plaats van automatisch te overschrijven. Controleer het beheer en verwijder verouderde feiten. Het model krijgt instructies om geen secrets op te slaan, maar dat is geen betrouwbare detector van alle gevoelige gegevens.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
node --test tests/test_extension.mjs
```

Node is uitsluitend nodig voor de JS-tests, niet om de toepassing te gebruiken. De DOM-test gebruikt een lokale HTML-fixture in headless Chrome (`/usr/bin/google-chrome`); geen account of netwerkverkeer naar Loes. Pas dit pad aan als Chrome elders staat. Servertests gebruiken deterministische testembeddings en een test-LLM, zodat API-logica offline controleerbaar is.

Bronnen voor de integratie: [Chrome content-scriptwerelden](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts), [serviceworker-netwerkrequests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests), [Open WebUI chatclient](https://github.com/open-webui/open-webui/blob/main/src/lib/apis/openai/index.ts), [Open WebUI antwoord-DOM](https://github.com/open-webui/open-webui/blob/main/src/lib/components/chat/Messages/ResponseMessage.svelte), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Echte lokale modelproef (vereist geïnstalleerde modellen, gebruikt een tijdelijke database):

```bash
.venv/bin/python -m scripts.smoke_local
```
