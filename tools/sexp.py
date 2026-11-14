"""Minimal KiCad s-expression reader/writer + symbol-library helpers."""
import os, re, copy

KICAD = r"C:\Users\Ryan\AppData\Local\Programs\KiCad\9.0"
SYMDIR = os.path.join(KICAD, "share", "kicad", "symbols")
FPDIR = os.path.join(KICAD, "share", "kicad", "footprints")


class Q(str):
    """quoted string (python value, escaped on output)"""


class QR(Q):
    """quoted string kept exactly as it appeared in the source file"""


_tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            break
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            top = stack.pop()
            stack[-1].append(top)
        elif m.group(3) is not None:
            stack[-1].append(QR(m.group(3)))
        else:
            stack[-1].append(m.group(4))
    return stack[0][0]


def dump(x, ind=0):
    if isinstance(x, list):
        simple = all(not isinstance(i, list) for i in x)
        if simple:
            return "(" + " ".join(dump(i) for i in x) + ")"
        out = "(" + dump(x[0])
        for i in x[1:]:
            if isinstance(i, list):
                out += "\n" + "\t" * (ind + 1) + dump(i, ind + 1)
            else:
                out += " " + dump(i)
        return out + "\n" + "\t" * ind + ")"
    if isinstance(x, Q):
        if isinstance(x, QR):
            return '"' + x + '"'
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    return str(x)


def find(node, tag):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == tag]


def first(node, tag):
    r = find(node, tag)
    return r[0] if r else None


_libcache = {}


def load_lib(lib):
    if lib not in _libcache:
        with open(os.path.join(SYMDIR, lib + ".kicad_sym"), encoding="utf8") as f:
            _libcache[lib] = parse(f.read())
    return _libcache[lib]


def get_symbol(lib, name):
    """Return a flattened (no 'extends') deep copy of a library symbol, named 'lib:name'."""
    root = load_lib(lib)
    syms = {s[1]: s for s in find(root, "symbol")}
    s = copy.deepcopy(syms[name])
    ext = first(s, "extends")
    if ext:
        parent = copy.deepcopy(syms[ext[1]])
        pname = parent[1]
        # child properties override parent's
        cprops = {p[1]: p for p in find(s, "property")}
        new = [parent[0], Q(name)]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in cprops:
                new.append(cprops[c[1]])
            elif isinstance(c, list) and c[0] == "symbol":
                c[1] = Q(c[1].replace(pname, name, 1))
                new.append(c)
            else:
                new.append(c)
        s = new
    s[1] = Q(lib + ":" + name)
    return s


def sym_pins(sym):
    """[(unit, number, name, etype, x, y, angle, length)]"""
    out = []
    for sub in find(sym, "symbol"):
        m = re.match(r".*_(\d+)_(\d+)$", sub[1])
        unit = int(m.group(1)) if m else 0
        for p in find(sub, "pin"):
            at = first(p, "at")
            out.append((unit, str(first(p, "number")[1]), str(first(p, "name")[1]), p[1],
                        float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0,
                        float(first(p, "length")[1])))
    return out


def sym_units(sym):
    us = set()
    for sub in find(sym, "symbol"):
        m = re.match(r".*_(\d+)_(\d+)$", sub[1])
        if m and int(m.group(1)) > 0:
            us.add(int(m.group(1)))
    return sorted(us) or [1]
