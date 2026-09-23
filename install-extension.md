# Chrome-extension installeren

1. Start de daemon met `./run.sh`; installeer eerst de lokale modellen zoals beschreven in README.md.
2. Open `chrome://extensions` in Chrome.
3. Zet **Developer mode / Ontwikkelaarsmodus** aan.
4. Klik **Load unpacked / Uitgepakte extensie laden**.
5. Selecteer de map **extension/** in dit project.
6. Open of herlaad **https://chat.loes.ai/** en log zoals gewoonlijk in.

De extension leest geen cookies en vraagt geen Loes-API-key. Laat `manifest.json` en de public key intact: de lokale daemon vertrouwt deze vaste extension-ID.

## Eerste proef

- Open http://127.0.0.1:8765/ en voeg een herkenbare voorkeur toe, bijvoorbeeld “Ik gebruik Linux en heb voorkeur voor terminalcommando’s.”
- Vraag Loes welke installatie-instructies bij jouw systeem passen.
- De gebruikersprompt moet gewoon zichtbaar blijven; in DevTools → Network → `chat/completions` zie je relevante context uitsluitend in de laatste user-payload.
- Vertel daarna een nieuwe stabiele voorkeur. Wacht tot het antwoord klaar is en Ollama de observatie heeft verwerkt. Herlaad het lokale beheer en controleer de memory.
- Open een nieuw gesprek en stel een relevante vervolgvraag.

DevTools → Console toont berichten met `[loes-memory]`, zonder gespreksteksten. `queued` betekent dat de observatie lokaal is aangenomen; controleer `/health` en de daemonterminal bij ontbrekende memories. De eerste model-load kan een recalltimeout veroorzaken; chatten gaat dan zonder context door.

Na codewijzigingen: klik **Reload** bij de extension en herlaad de Loes-tab. Werkt de DOM-detectie niet meer, pas de centrale selectors in `config.js` aan. Deze proof-of-concept ondersteunt de standaard Open WebUI-fetchroute; de daadwerkelijke Loes-versie moet met bovenstaande proef gecontroleerd worden.

## Update 0.1.1: geladen maar geen geheugenactiviteit

Versie 0.1.0 kon stilzwijgend alle prompts overslaan doordat Chrome `config.js` niet opnieuw uitvoerde in de tweede scriptomgeving. Versie 0.1.1 draagt de configuratie expliciet over. Na bijwerken moet je **zowel de extension als de Loes-tab herladen**. Controleer dat de extensionkaart versie 0.1.1 toont.

Na een verzonden tekstbericht zie je in de Loes-console (zet ook Debug/Verbose aan) `[loes-memory] Chatprompt doorgestuurd met ... herinneringen.` Na het antwoord volgt `Lokale observatie: queued`. Bij een leeg geheugen is nul herinneringen normaal; de observatie moet wel plaatsvinden. Verborgen configuratie- en verbindingsfouten geven nu een waarschuwing.
