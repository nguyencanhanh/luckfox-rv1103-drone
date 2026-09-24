#!/usr/bin/env python3
"""Minimal KiCad s-expression reader/writer plus symbol-library helpers.

Only what the AQUANODE generators need: parse a .kicad_sym file, resolve
`extends`, hand back pin geometry, and re-serialise a symbol so it can be
embedded in a schematic's (lib_symbols ...) block.
"""

import os

SS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "lib", "symbols")


class Atom(str):
    """A bare symbol/number token - serialised without quotes."""
    __slots__ = ()


def tokenize(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            out.append(str("".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            out.append(Atom(text[i:j]))
            i = j
    return out


def parse(text):
    tokens = tokenize(text)
    pos = [0]

    def build():
        assert tokens[pos[0]] == "(", tokens[pos[0]]
        pos[0] += 1
        node = []
        while tokens[pos[0]] != ")":
            if tokens[pos[0]] == "(":
                node.append(build())
            else:
                node.append(tokens[pos[0]])
                pos[0] += 1
        pos[0] += 1
        return node

    return build()


def esc(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump(node, indent=0):
    if not isinstance(node, list):
        return node if isinstance(node, Atom) else esc(node)
    pad = "\t" * indent
    head = node[0] if node else Atom("")
    simple = all(not isinstance(c, list) for c in node[1:])
    if simple:
        return pad + "(" + " ".join(
            [dump(head)] + [dump(c) for c in node[1:]]) + ")"
    parts = [pad + "(" + dump(head)]
    for c in node[1:]:
        if isinstance(c, list):
            parts.append(dump(c, indent + 1))
        else:
            parts[-1] += " " + dump(c)
    parts.append(pad + ")")
    return "\n".join(parts)


def tag(node, name, default=None):
    for c in node:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return default


def tags(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def walk(node, name):
    if isinstance(node, list):
        if node and node[0] == name:
            yield node
        for c in node:
            yield from walk(c, name)


# ---------------------------------------------------------------------------
_LIB_CACHE = {}


def load_lib(libname):
    if libname in _LIB_CACHE:
        return _LIB_CACHE[libname]
    for base in (LOCAL, SS):
        p = os.path.join(base, libname + ".kicad_sym")
        if os.path.exists(p):
            root = parse(open(p).read())
            syms = {s[1]: s for s in tags(root, "symbol")}
            _LIB_CACHE[libname] = syms
            return syms
    raise KeyError("symbol library not found: " + libname)


def get_symbol(lib_id):
    """Return a *flattened* symbol node (extends resolved), named `lib_id`."""
    lib, name = lib_id.split(":", 1)
    syms = load_lib(lib)
    if name not in syms:
        raise KeyError("symbol %s not in %s" % (name, lib))
    sym = syms[name]
    ext = tag(sym, "extends")
    if ext:
        parent = syms[ext[1]]
        # keep the child's properties + flags, take the parent's drawing units
        child_props = {p[1] for p in tags(sym, "property")}
        merged = [str(lib_id)]
        for c in sym[2:]:
            if isinstance(c, list) and c[0] != "extends":
                merged.append(c)
        for c in parent[2:]:
            if not isinstance(c, list):
                continue
            if c[0] == "property" and c[1] in child_props:
                continue
            if c[0] == "extends":
                continue
            merged.append(_rename_unit(c, ext[1], name))
        node = merged
    else:
        node = [str(lib_id)] + [c for c in sym[2:]]
        node = [node[0]] + [_rename_unit(c, name, name) for c in node[1:]]
    return node


def _rename_unit(node, old_root, new_root):
    """Sub-symbol units are named `<root>_<unit>_<style>`; keep them unique."""
    if isinstance(node, list) and node and node[0] == "symbol" \
            and isinstance(node[1], str) and node[1].startswith(old_root + "_"):
        node = [node[0], str(new_root + node[1][len(old_root):])] + node[2:]
    return node


def pin_geometry(lib_id):
    """{unit: [(number, name, etype, x, y, angle, length), ...]}"""
    sym = get_symbol(lib_id)
    out = {}
    for sub in tags(sym, "symbol"):
        # name is "<root>_<unit>_<style>"
        try:
            unit = int(sub[1].rsplit("_", 2)[-2])
        except (ValueError, IndexError):
            unit = 1
        for p in tags(sub, "pin"):
            at = tag(p, "at")
            num = tag(p, "number")[1]
            nm = tag(p, "name")[1]
            ln = tag(p, "length")
            out.setdefault(unit, []).append(
                (num, nm, str(p[1]), float(at[1]), float(at[2]),
                 float(at[3]) if len(at) > 3 else 0.0,
                 float(ln[1]) if ln else 2.54))
    # unit 0 is the "common" unit - its pins belong to every real unit
    common = out.pop(0, [])
    if common:
        if not out:
            out[1] = []
        for u in out:
            out[u] = common + out[u]
    return out


def body_bbox(lib_id, unit=1):
    """Rough bbox of the drawing (excluding pins) for one unit, plus pins."""
    sym = get_symbol(lib_id)
    xs, ys = [], []
    for sub in tags(sym, "symbol"):
        try:
            u = int(sub[1].rsplit("_", 2)[-2])
        except (ValueError, IndexError):
            u = 0
        if u not in (0, unit):
            continue
        for kind in ("rectangle", "polyline", "circle", "arc"):
            for g in tags(sub, kind):
                for key in ("start", "end", "center", "mid", "at"):
                    t = tag(g, key)
                    if t:
                        xs.append(float(t[1]))
                        ys.append(float(t[2]))
                pts = tag(g, "pts")
                if pts:
                    for xy in tags(pts, "xy"):
                        xs.append(float(xy[1]))
                        ys.append(float(xy[2]))
        for p in tags(sub, "pin"):
            at = tag(p, "at")
            xs.append(float(at[1]))
            ys.append(float(at[2]))
    if not xs:
        return (-1.27, -1.27, 1.27, 1.27)
    return (min(xs), min(ys), max(xs), max(ys))


def units_of(lib_id):
    g = pin_geometry(lib_id)
    return sorted(g) or [1]
