import json
import os
import requests
import sys

POSSIBLE_PATHS = [
    os.path.expandvars(r"%USERPROFILE%/AppData/Local/github-copilot/intellij/mcp.json"),
    os.path.expanduser(r"~\\AppData\\Local\\github-copilot\\intellij\\mcp.json"),
    r"C:\\Users\\the_h\\AppData\\Local\\github-copilot\\intellij\\mcp.json",
]

def find_mcp():
    for p in POSSIBLE_PATHS:
        if os.path.exists(p):
            return p
    return None

def main():
    path = find_mcp()
    if not path:
        print("No se encontró mcp.json en las rutas esperadas:")
        for p in POSSIBLE_PATHS:
            print(" -", p)
        sys.exit(1)

    print(f"Usando mcp.json: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        mcp = json.load(f)

    server = mcp.get('servers', {}).get('asana-mcp')
    if not server:
        print('mcp.json no contiene servers.asana-mcp')
        sys.exit(1)

    url = server.get('url')
    headers = server.get('requestInit', {}).get('headers', {})
    print('POST ->', url)
    print('Headers:', headers)
    # Try GET first (some MCP endpoints use GET to establish streaming)
    try:
        print('\n--> Trying GET to the MCP endpoint')
        r = requests.get(url, headers=headers, timeout=15)
        print('GET Status:', r.status_code)
        print('GET Body:', r.text[:1000])
    except Exception as e:
        print('GET failed:', repr(e))

    # Candidate JSON-RPC methods that might create/register a session
    create_methods = [
        'createSession', 'session.create', 'mcp.createSession', 'mcp.session.create',
        'session.start', 'mcp.start', 'mcp.init', 'session.init', 'open', 'connect'
    ]

    for method in create_methods:
        payload = {"jsonrpc": "2.0", "method": method, "params": {}, "id": 1}
        print('\n--> Trying method:', method)
        print('Payload:', json.dumps(payload))
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=15)
            print('Status:', r.status_code)
            print('Body:', r.text)
        except requests.exceptions.RequestException as e:
            print('Request failed:', repr(e))
            if hasattr(e, 'response') and e.response is not None:
                print('Response status:', e.response.status_code)
                try:
                    print(e.response.text)
                except Exception:
                    pass

if __name__ == '__main__':
    main()

