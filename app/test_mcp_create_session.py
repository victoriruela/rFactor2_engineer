import json
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
headers = cfg['servers']['asana-mcp']['requestInit']['headers']
sid = headers.get('Mcp-Session-Id')

def try_post(u, payload):
    print('\nPOST ->', u)
    print('Payload:', json.dumps(payload))
    r = requests.post(u, json=payload, headers=headers, timeout=15)
    print('Status', r.status_code)
    print('Body', r.text)

payloads = [
    (url, {"jsonrpc":"2.0","method":"mcp.createSession","params":{"sessionId":sid},"id":1}),
    (url, {"jsonrpc":"2.0","method":"mcp.createSession","params":{"session_id":sid},"id":1}),
    (url, {"jsonrpc":"2.0","method":"createSession","params":{"sessionId":sid},"id":1}),
    (url + f"?sessionId={sid}", {"jsonrpc":"2.0","method":"mcp.createSession","params":{},"id":1}),
    (url + f"/{sid}", {"jsonrpc":"2.0","method":"mcp.createSession","params":{},"id":1}),
    (url, {"jsonrpc":"2.0","method":"connect","params":{"sessionId":sid},"id":1}),
    (url, {"jsonrpc":"2.0","method":"mcp.connect","params":{"sessionId":sid},"id":1}),
    (url, {"jsonrpc":"2.0","method":"handshake","params":{"sessionId":sid},"id":1}),
    (url, {"jsonrpc":"2.0","method":"register","params":{"sessionId":sid, "client_id": "%s"},"id":1}),
]

for u,p in payloads:
    try:
        try_post(u,p)
    except Exception as e:
        print('ERROR', e)

print('\nDone')

