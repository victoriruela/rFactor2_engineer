import json
import uuid
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

methods = [
    'mcp.createSession', 'createSession', 'mcp.connect', 'connect', 'mcp.init', 'init',
    'register', 'handshake', 'session.create', 'session.init'
]

def do_get(headers):
    print('\nGET ->', url)
    print('Headers:', headers)
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print('GET Status:', r.status_code)
        print('GET Body:', r.text[:1000])
    except Exception as e:
        print('GET failed:', repr(e))

def do_post(method, headers, payload_params=None):
    payload = {"jsonrpc": "2.0", "method": method, "params": payload_params or {}, "id": 1}
    print('\nPOST ->', url)
    print('Method:', method)
    print('Headers:', headers)
    print('Payload:', json.dumps(payload))
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        print('Status:', r.status_code)
        print('Body:', r.text)
        return r
    except Exception as e:
        print('Request failed:', repr(e))
        return None

def main():
    client_sid = str(uuid.uuid4())
    print('Client-generated SID for tests:', client_sid)

    # Prepare headers with and without Mcp-Session-Id
    headers_base = {k: v for k, v in orig_headers.items()}
    headers_with_sid = dict(headers_base)
    headers_with_sid['Mcp-Session-Id'] = client_sid
    headers_without_sid = {k: v for k, v in headers_base.items() if k.lower() != 'mcp-session-id'}

    print('\n=== Try GET without Mcp-Session-Id ===')
    do_get(headers_without_sid)
    print('\n=== Try GET with Mcp-Session-Id ===')
    do_get(headers_with_sid)

    for method in methods:
        print('\n=== Trying method WITHOUT Mcp-Session-Id ===')
        r1 = do_post(method, headers_without_sid)

        print('\n=== Trying method WITH Mcp-Session-Id (client SID) ===')
        r2 = do_post(method, headers_with_sid)

        # Also try sending sessionId as param (both naming conventions)
        print('\n=== Trying method WITH sessionId param (sessionId key) and header ===')
        r3 = do_post(method, headers_with_sid, payload_params={"sessionId": client_sid})

        print('\n=== Trying method WITH session_id param (session_id key) and header ===')
        r4 = do_post(method, headers_with_sid, payload_params={"session_id": client_sid})

    print('\nExhaustive tests finished.')

if __name__ == '__main__':
    main()

