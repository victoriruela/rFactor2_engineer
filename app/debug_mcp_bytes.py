from pathlib import Path

path = Path(r"C:\Users\the_h\AppData\Local\github-copilot\intellij\mcp.json")
print('Path:', path)
s = path.read_bytes()
print('File length:', len(s))
try:
    txt = s.decode('utf-8')
    print('Decoded OK, sample (first 300 chars):')
    print(txt[:300])
except Exception as e:
    print('Decode error:', e)

# Show repr of bytes around the reported position (char 545)
pos = 545
start = max(0, pos-40)
end = min(len(s), pos+40)
print('\nBytes repr around pos {}:'.format(pos))
print(repr(s[start:end]))

# List control characters (0x00-0x1f) positions
controls = [(i, b) for i, b in enumerate(s) if b < 0x20]
print('\nFound {} control bytes (value<0x20)'.format(len(controls)))
for i, b in controls[:50]:
    print(f'  idx={i} byte=0x{b:02x} char={repr(chr(b))}')

print('\nDone')

import json
try:
    obj = json.loads(txt)
    print('\njson.loads succeeded; keys at top level:', list(obj.keys()))
except Exception as e:
    print('\njson.loads failed with exception:')
    import traceback
    traceback.print_exc()


