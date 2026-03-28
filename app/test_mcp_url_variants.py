import json
import uuid
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
base_url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

client_sid = str(uuid.uuid4())
headers_with_sid = dict(orig_headers)
headers_with_sid['Mcp-Session-Id'] = client_sid
headers_without_sid = {k: v for k, v in orig_headers.items() if k.lower() != 'mcp-session-id'}

def try_post(u, headers, params=None):
    payload = {"jsonrpc":"2.0","method":"mcp.createSession","params":params or {},"id":1}
    print('\nPOST ->', u)
    print('Headers:', headers)
    print('Payload:', json.dumps(payload))
    try:
        r = requests.post(u, json=payload, headers=headers, timeout=15)
        print('Status', r.status_code)
        print('Body', r.text)
    except Exception as e:
        print('ERROR', e)

def main():
    print('Base URL:', base_url)
    urls = [
        base_url,
        base_url + '/' + client_sid,
        base_url + '?sessionId=' + client_sid,
        base_url + '/connect',
        base_url + '/v2/mcp/' + client_sid
    ]

    for u in urls:
        print('\n=== WITHOUT Mcp-Session-Id header ===')
        try_post(u, headers_without_sid)
        print('\n=== WITH Mcp-Session-Id header ===')
        try_post(u, headers_with_sid)

if __name__ == '__main__':
    main()

