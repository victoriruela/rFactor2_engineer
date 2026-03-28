import json
import uuid
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

def do_post(u, payload, headers, timeout=15):
    print('\nPOST ->', u)
    print('Headers:', headers)
    print('Payload:', json.dumps(payload))
    r = requests.post(u, json=payload, headers=headers, timeout=timeout)
    print('Status', r.status_code)
    print('Body', r.text)
    return r

def main():
    client_sid = str(uuid.uuid4())
    headers = dict(orig_headers)
    headers['Mcp-Session-Id'] = client_sid

    print('Using client-generated Mcp-Session-Id:', client_sid)

    payload = {"jsonrpc": "2.0", "method": "mcp.createSession", "params": {}, "id": 1}
    try:
        r = do_post(url, payload, headers)
    except Exception as e:
        print('ERROR initial request', e)
        return

    if r.status_code != 200:
        print('\nInitial request failed; response above.')
        return

    try:
        body = r.json()
    except Exception:
        print('Response is not JSON; aborting')
        return

    print('\nInitial response JSON:\n', json.dumps(body, indent=2))

    # If server returns a sessionId, show it. Also demonstrate a follow-up connect call
    sid = None
    if 'result' in body and isinstance(body['result'], dict):
        sid = body['result'].get('sessionId') or body['result'].get('session_id')

    if sid:
        print('\nServer returned sessionId:', sid)
    else:
        print('\nServer did not return a sessionId in result.')

    # Follow-up: attempt mcp.connect with header containing client_sid
    payload2 = {"jsonrpc": "2.0", "method": "mcp.connect", "params": {}, "id": 2}
    try:
        r2 = do_post(url, payload2, headers)
    except Exception as e:
        print('ERROR follow-up request', e)
        return

    print('\nDone')

if __name__ == '__main__':
    main()

