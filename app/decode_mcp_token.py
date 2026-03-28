import json
import base64
from pathlib import Path

def b64pad(s):
    return s + '=' * (-len(s) % 4)

def decode_jwt_noverify(token):
    parts = token.split('.')
    if len(parts) < 2:
        raise ValueError('Not a JWT')
    payload_b64 = parts[1]
    payload_json = base64.urlsafe_b64decode(b64pad(payload_b64)).decode('utf-8')
    return json.loads(payload_json)

def main():
    path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
    mcp = json.loads(path.read_text(encoding='utf-8'))
    auth = mcp['servers']['asana-mcp']['requestInit']['headers'].get('Authorization')
    if not auth:
        print('No Authorization header found in mcp.json')
        return
    if not auth.lower().startswith('bearer '):
        print('Authorization header is not Bearer token:', auth)
        return
    token = auth.split(' ',1)[1]
    try:
        payload = decode_jwt_noverify(token)
    except Exception as e:
        print('Failed to decode token:', e)
        return
    print('Decoded JWT payload:')
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()

