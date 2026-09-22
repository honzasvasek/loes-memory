"""Real browser DOM test against a local fixture; no requests to Loes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_streaming_dom_and_navigation():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        page.route('https://chat.loes.ai/**', lambda route: route.fulfill(body='''<!doctype html><div id="chat-input" contenteditable="true" role="textbox"></div><main></main>''', content_type='text/html'))
        page.goto('https://chat.loes.ai/c/chat1')
        page.evaluate('''() => {
            window.observations = [];
            window.chrome = {runtime: {sendMessage: async message => {
                if (message.action === 'observe') observations.push(message.body);
                return {ok:true, data:{status:'ok', memories:[]}};
            }}};
        }''')
        for filename in ['config.js', 'content.js']:
            page.add_script_tag(content=Path('extension', filename).read_text())
        page.evaluate('''() => {
            window.postMessage({source:'loes-memory-page',action:'sent',id:'req1',user:'Originele vraag',responseId:'answer1',chatId:'chat1'}, location.origin);
            window.postMessage({source:'loes-memory-page',action:'accepted',id:'req1'}, location.origin);
            document.querySelector('main').innerHTML = '<div id="message-answer1"><div id="response-content-container"><p>Een half</p></div></div><button aria-label="Stop">Stop</button>';
        }''')
        page.wait_for_timeout(2000)
        assert page.evaluate('observations.length') == 0
        page.evaluate('''() => {
            document.querySelector('#response-content-container').innerHTML = '<p>Het volledige antwoord.</p><button>Code kopiëren</button>';
            document.querySelector('[aria-label="Stop"]').remove();
            document.querySelector('#message-answer1').insertAdjacentHTML('beforeend','<button class="copy-response-button">Copy</button>');
        }''')
        page.wait_for_function('observations.length === 1')
        observation = page.evaluate('observations[0]')
        assert observation['user'] == 'Originele vraag'
        assert observation['assistant'] == 'Het volledige antwoord.'
        page.wait_for_timeout(1600)
        assert page.evaluate('observations.length') == 1
        # A second turn must not capture an answer after switching to another conversation.
        page.evaluate('''() => {
            window.postMessage({source:'loes-memory-page',action:'sent',id:'req2',user:'Vraag twee',responseId:'answer2',chatId:'chat1'}, location.origin);
            window.postMessage({source:'loes-memory-page',action:'accepted',id:'req2'}, location.origin);
        }''')
        page.wait_for_timeout(100)
        page.evaluate('''() => {
            history.pushState({},'', '/c/other');
            document.querySelector('main').innerHTML = '<div id="message-answer2"><div id="response-content-container">Verkeerd gesprek</div><button class="copy-response-button">Copy</button></div>';
        }''')
        page.wait_for_timeout(2200)
        assert page.evaluate('observations.length') == 1
        browser.close()
