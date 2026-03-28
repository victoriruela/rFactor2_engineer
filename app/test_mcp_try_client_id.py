import json
import uuid
from pathlib import Path
import requests
import importlib.util

# Load CLIENT_ID from asana_mcp_oauth2.py without package import
spec = importlib.util.spec_from_file_location('asana_mcp_oauth2', r'C:\PythonProjects\rFactor2_engineer\app\asana_mcp_oauth2.py')
oauth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oauth)

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

client_sid = str(uuid.uuid4())
headers = dict(orig_headers)
headers['Mcp-Session-Id'] = client_sid
headers.setdefault('Content-Type', 'application/json')

methods = ['mcp.createSession', 'createSession', 'register', 'mcp.connect']
param_variants = [
    {},
    {'client_id': oauth.CLIENT_ID},
    {'clientId': oauth.CLIENT_ID},
    {'app': oauth.CLIENT_ID},
    {'client_id': oauth.CLIENT_ID, 'app': oauth.CLIENT_ID}
]

def try_combo(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    print('\n--- Trying', method, 'with params', params)
    print('Headers:', headers)
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        print('Status:', r.status_code)
        print('Body:', r.text)
    except Exception as e:
        print('ERROR', e)

def main():
    print('Using Mcp-Session-Id:', client_sid)
    for m in methods:
        for p in param_variants:
            try_combo(m, p)

if __name__ == '__main__':
    main()

