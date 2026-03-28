import json
import threading
import time
import uuid
from pathlib import Path
import requests

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
cfg = json.loads(path.read_text(encoding='utf-8'))
url = cfg['servers']['asana-mcp']['url']
orig_headers = cfg['servers']['asana-mcp']['requestInit']['headers']

sid = str(uuid.uuid4())
headers = dict(orig_headers)
headers['Mcp-Session-Id'] = sid

def do_stream_get():
    print('Starting streaming GET (will read up to 4096 bytes or timeout 10s)')
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=10)
        print('GET status:', r.status_code)
        try:
            chunk = next(r.iter_content(chunk_size=4096))
            print('First chunk length:', len(chunk))
            print('First chunk (decoded):', chunk.decode('utf-8', errors='replace')[:1000])
        except StopIteration:
            print('No content received from streaming GET')
        finally:
            r.close()
    except Exception as e:
        print('Streaming GET error:', e)

def do_post_create():
    payload = {"jsonrpc": "2.0", "method": "mcp.createSession", "params": {}, "id": 1}
    print('\nPOST ->', url)
    print('Headers:', headers)
    print('Payload:', json.dumps(payload))
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        print('POST status:', r.status_code)
        print('POST body:', r.text)
        try:
            print('POST json:', json.dumps(r.json(), indent=2))
        except Exception:
            pass
    except Exception as e:
        print('POST error:', e)

def main():
    print('Using Mcp-Session-Id:', sid)
    t = threading.Thread(target=do_stream_get, daemon=True)
    t.start()
    time.sleep(0.5)
    do_post_create()
    t.join(timeout=5)

if __name__ == '__main__':
    main()

