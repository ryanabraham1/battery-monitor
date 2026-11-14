import re, sys
t = open(sys.argv[1], encoding='utf8').read()
blocks = re.split(r'\n(?=\[)', t)
seen = {}
for b in blocks:
    m = re.match(r'\[(\w+)\]', b)
    if m:
        seen.setdefault(m.group(1), []).append(b)
lim = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for k, v in seen.items():
    print('=====', k, len(v))
    for b in v[:lim]:
        lines = [l.strip() for l in b.strip().split('\n') if l.strip() and not l.strip().startswith('**')]
        print('   ' + ' | '.join(lines)[:330])
print(' '.join(re.findall(r'\*\* Found .*? \*\*', t)))
