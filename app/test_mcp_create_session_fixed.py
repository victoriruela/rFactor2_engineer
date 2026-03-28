import json
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

# Build headers for initial initialization: MUST NOT include Mcp-Session-Id
headers_init = {k: v for k, v in orig_headers.items() if k.lower() != 'mcp-session-id'}

def do_post(u, payload, headers, timeout=15):
    print('\nPOST ->', u)
    print('Headers:', headers)
    print('Payload:', json.dumps(payload))
    r = requests.post(u, json=payload, headers=headers, timeout=timeout)
    print('Status', r.status_code)
    print('Body', r.text)
    return r

def main():
    # 1) Initial JSON-RPC initialization - no session id header and no sessionId param
    payload_init = {"jsonrpc": "2.0", "method": "mcp.createSession", "params": {}, "id": 1}
    try:
        r = do_post(url, payload_init, headers_init)
    except Exception as e:
        print('ERROR initial request', e)
        return

    if r.status_code != 200:
        print('\nInitial request failed; check response above.\nIf you get 400 with message about sessionId, ensure no Mcp-Session-Id header is sent and params is empty.')
        return

    try:
        body = r.json()
    except Exception:
        print('Response is not JSON; aborting')
        return

    # Try to extract sessionId from result (common key names: sessionId, session_id)
    sid = None
    if 'result' in body and isinstance(body['result'], dict):
        sid = body['result'].get('sessionId') or body['result'].get('session_id')

    if not sid:
        print('No sessionId returned in initial response. Response JSON:\n', json.dumps(body, indent=2))
        return

    print('\nGot sessionId from server:', sid)

    # 2) Make a follow-up request with Mcp-Session-Id header set (or original header modified)
    headers_with_sid = dict(orig_headers)
    headers_with_sid['Mcp-Session-Id'] = sid

    # Try a connect/createSession call now that we have the session id
    payload_follow = {"jsonrpc": "2.0", "method": "mcp.connect", "params": {"sessionId": sid}, "id": 2}
    try:
        r2 = do_post(url, payload_follow, headers_with_sid)
    except Exception as e:
        print('ERROR follow-up request', e)
        return

    print('\nDone')

if __name__ == '__main__':
    main()

