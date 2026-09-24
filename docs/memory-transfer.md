# Geheugen overzetten uit ChatGPT of andere chatbots

Vraag de bronchatbot om de onderstaande prompt uit te voeren. De prompt werkt ook
voor andere chatbots; wat beschikbaar is verschilt per product en account. Een
chatbot kan niet automatisch al je oude gesprekken inzien. Controleer daarom
zelf de export, vooral oude voorkeuren, onzekere feiten en gevoelige informatie.

Sla het antwoord als UTF-8 JSON op, bijvoorbeeld in `imports/chatGPTmemorie.json`.
Verwijder eventuele Markdown-codeblokken rondom de JSON. De map `imports/` en
JSON-bestanden in de projectroot staan in `.gitignore`; zet persoonlijke exports
niet in andere gevolgde mappen en gebruik geen `git add -f`.

## Importeren

Voer vanuit de projectmap uit, nadat de dependencies en het lokale embeddingmodel
zijn geïnstalleerd zoals beschreven in de README:

```bash
# Controleer het volledige bestand zonder database- of modeltoegang:
.venv/bin/python -m scripts.import_memories imports/chatGPTmemorie.json --dry-run

# Importeer naar de database die in .env staat:
.venv/bin/python -m scripts.import_memories imports/chatGPTmemorie.json
```

Een bestand in de projectroot werkt ook:
` .venv/bin/python -m scripts.import_memories chatGPTmemorie.json `.

De import schrijft rechtstreeks naar de lokale SQLite-database. De daemon hoeft
niet te draaien; een draaiende daemon ziet de wijzigingen direct. Er zijn geen
API-key, cloudservice of Ollama-aanroep nodig. Lokale embeddings worden gemaakt
voor de zoekfunctie en semantische duplicaatcontrole.

De uitvoer toont alleen aantallen. Eerst wordt het hele bestand gevalideerd, daarna
worden embeddings berekend en alle nieuwe memories in één transactie opgeslagen.
Bij een fout wordt niets uit die import toegevoegd. Exitcode 0 betekent succes,
1 betekent een fout. Een lege lijst is geldig en wijzigt niets.

Herhalen is veilig: exacte duplicaten en sterk gelijkende teksten van hetzelfde
type worden overgeslagen, ook binnen één bestand. De bestaande tekst, importance
en confidence blijven daarbij behouden. Semantische deduplicatie is een heuristiek:
controleer gewijzigde of tegengestelde voorkeuren zelf in het
[lokale beheer](http://127.0.0.1:8765/). Er is geen automatische feitencontrole of
secret-detector. Importeer alleen informatie die je wilt bewaren én later als
relevante context naar Loes wilt laten meesturen.

Het programma accepteert een object met `memories` en optioneel `limitations`,
of een losse lijst. `limitations` wordt niet als memory opgeslagen. Per item:
`type` is `profile` of `episodic`, `text` bevat 1–1000 tekens,
`importance` en `confidence` zijn getallen van 0 tot 1 (defaults: 0.5 en 1).
Onbekende velden worden geweigerd. Maximaal 10 MiB en 10.000 items per bestand.
Creatie- en wijzigingsdatum worden bij import gezet; historische gebeurtenisdatums
horen in de tekst.

## Overdrachtsprompt

Kopieer de volgende tekst naar de chatbot waarvan je herinneringen wilt exporteren:

```text
Ik wil mijn persoonlijke gegevens exporteren naar een lokaal geheugensysteem voor Loes.ai.

Gebruik uitsluitend informatie over mij die daadwerkelijk voor jou beschikbaar is:
opgeslagen herinneringen, deze conversatie en eventuele beschikbare context uit
eerdere chats. Veronderstel niet dat je mijn volledige chatgeschiedenis kunt inzien.
Beschrijf je toegangsbeperkingen kort in het JSON-veld "limitations".

Selecteer informatie die waarschijnlijk later nuttig is:
- naam, achtergrond en terugkerende personen of organisaties;
- interesses, projecten en doelen;
- communicatievoorkeuren en technische voorkeuren;
- belangrijke gebeurtenissen, besluiten en gewijzigde plannen.

Regels:
- Eén zelfstandig begrijpelijk feit per herinnering.
- Schrijf in het Nederlands, compact maar zonder belangrijke nuances te verliezen.
- Geen duplicaten, onbevestigde aannames, fictieve testgegevens of voorbeeldgegevens.
- Behandel uitspraken van de assistant niet als feiten over mij.
- Vermeld bij projectgebonden voorkeuren voor welk project ze gelden.
- Bewaar tijdelijke details alleen als ze later betekenis hebben.
- Neem geen wachtwoorden, API-keys, cookies, inloggegevens of andere geheimen op.
- Verzin geen datums. Vermeld bekende datums bij gebeurtenissen in de tekst.
- Bij tegenstrijdigheden: gebruik de recentste expliciete correctie als die bekend
  is; vermeld anders de onzekerheid.
- "importance" en "confidence" zijn getallen tussen 0 en 1.
- Gebruik "profile" voor relatief stabiele feiten en "episodic" voor gebeurtenissen
  of besluiten.
- Houd iedere herinnering onder 1000 tekens.
- Voeg geen andere velden toe.

Geef uitsluitend geldige JSON terug, zonder Markdown-codeblok of begeleidende tekst,
in exact deze structuur (vervang de voorbeelditems door echte feiten):

{
  "limitations": "Welke geheugenbronnen je daadwerkelijk kunt gebruiken en welke beperkingen daarbij gelden.",
  "memories": [
    {
      "type": "profile",
      "text": "Een concreet feit over mij.",
      "importance": 0.8,
      "confidence": 0.95
    },
    {
      "type": "episodic",
      "text": "Een betekenisvolle gebeurtenis of beslissing, met datum indien bekend.",
      "importance": 0.7,
      "confidence": 0.9
    }
  ]
}

Als je geen betrouwbare persoonlijke informatie beschikbaar hebt, geef dan een lege
memories-lijst. Volledigheid is minder belangrijk dan juistheid.
```
